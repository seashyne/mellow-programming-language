static void *heap_alloc(MVM *vm, size_t count, size_t item_size, MHeapKind kind) {
    size_t bytes = count * item_size;
    void *ptr;
    MHeapBlock *block;
    if (!vm) return calloc(count ? count : 1, item_size ? item_size : 1);
    ptr = calloc(count ? count : 1, item_size ? item_size : 1);
    if (!ptr) return NULL;
    block = (MHeapBlock *)calloc(1, sizeof(MHeapBlock));
    if (!block) { free(ptr); return NULL; }
    block->ptr = ptr;
    block->bytes = bytes;
    block->kind = kind;
    block->owner = vm;
    /* Index before linking: a table grow rehashes g_heap_blocks, and the new
       block must not be inserted twice. */
    heap_index_insert(block);
    block->next = g_heap_blocks;
    g_heap_blocks = block;
    vm->heap_allocated++;
    vm->heap_live++;
    vm->heap_blocks++;
    vm->heap_bytes += bytes;
    return ptr;
}

static void heap_mark_value(MVM *vm, const MValue *value);

static void heap_mark_ptr(MVM *vm, const void *ptr) {
    MHeapBlock *block = heap_find(ptr);
    if (!block || block->owner != vm || block->marked) return;
    block->marked = 1;
}

static void heap_mark_value(MVM *vm, const MValue *value) {
    size_t i;
    if (!vm || !value) return;
    switch (value->tag) {
    case MVAL_STR:
        heap_mark_ptr(vm, value->as.str.ptr);
        break;
    case MVAL_LIST:
        heap_mark_ptr(vm, value->as.list.items);
        for (i = 0; i < value->as.list.len; ++i)
            heap_mark_value(vm, &value->as.list.items[i]);
        break;
    case MVAL_MAP:
        heap_mark_ptr(vm, value->as.map.keys);
        heap_mark_ptr(vm, value->as.map.values);
        for (i = 0; i < value->as.map.len; ++i) {
            heap_mark_value(vm, &value->as.map.keys[i]);
            heap_mark_value(vm, &value->as.map.values[i]);
        }
        break;
    default:
        break;
    }
}

void mvm_gc_mark_value(MVM *vm, const MValue *value) {
    heap_mark_value(vm, value);
}

uint64_t mvm_gc_collect_with_marker(MVM *vm, void (*marker)(void *user, MVM *vm), void *user) {
    MHeapBlock *block;
    MHeapBlock *prev = NULL;
    MHeapBlock *next;
    uint64_t freed = 0;
    uint64_t freed_bytes = 0;
    size_t i;
    if (!vm) return 0;
    for (block = g_heap_blocks; block; block = block->next)
        if (block->owner == vm) block->marked = 0;
    for (i = 0; i < vm->stack_len; ++i) heap_mark_value(vm, &vm->stack[i]);
    for (i = 0; i < vm->locals_len; ++i) heap_mark_value(vm, &vm->locals[i]);
    for (i = 0; i < vm->task_len; ++i) {
        MTask *task = &vm->tasks[i];
        size_t j;
        if (!task->active || task->finished || i == vm->current_task) continue;
        for (j = 0; j < task->stack_len; ++j) heap_mark_value(vm, &task->stack[j]);
        for (j = 0; j < task->locals_len; ++j) heap_mark_value(vm, &task->locals[j]);
    }
    if (marker) marker(user, vm);
    block = g_heap_blocks;
    while (block) {
        next = block->next;
        if (block->owner == vm && !block->marked) {
            {
                size_t block_bytes = block->bytes;
                freed_bytes += block_bytes;
                if (vm->heap_bytes >= block_bytes) vm->heap_bytes -= block_bytes;
                else vm->heap_bytes = 0;
            }
            if (prev) prev->next = next;
            else g_heap_blocks = next;
            heap_index_remove(block);
            free(block->ptr);
            free(block);
            freed++;
            vm->heap_freed++;
            if (vm->heap_live > 0) vm->heap_live--;
            if (vm->heap_blocks > 0) vm->heap_blocks--;
        } else {
            prev = block;
        }
        block = next;
    }
    vm->heap_last_gc_freed = freed;
    vm->heap_last_gc_freed_bytes = freed_bytes;
    return freed;
}

uint64_t mvm_gc_collect(MVM *vm) {
    return mvm_gc_collect_with_marker(vm, NULL, NULL);
}

static int ensure_stack(MVM *vm, size_t cap) {
    if (vm->stack_cap >= cap) return 1;
    size_t next = vm->stack_cap ? vm->stack_cap * 2 : 64;
    if (next < cap) next = cap;
    MValue *p = (MValue *)realloc(vm->stack, sizeof(MValue) * next);
    if (!p) return 0;
    vm->stack = p; vm->stack_cap = next; return 1;
}
static int ensure_frames(MVM *vm, size_t cap) {
    if (vm->frame_cap >= cap) return 1;
    size_t next = vm->frame_cap ? vm->frame_cap * 2 : 16;
    if (next < cap) next = cap;
    MFrame *p = (MFrame *)realloc(vm->frames, sizeof(MFrame) * next);
    if (!p) return 0;
    vm->frames = p; vm->frame_cap = next; return 1;
}
int mvm_reserve_locals(MVM *vm, size_t cap) {
    if (vm->locals_cap >= cap) return 1;
    size_t next = vm->locals_cap ? vm->locals_cap * 2 : 64;
    if (next < cap) next = cap;
    MValue *p = (MValue *)realloc(vm->locals, sizeof(MValue) * next);
    if (!p) return 0;
    for (size_t i = vm->locals_cap; i < next; ++i) p[i] = mval_none();
    vm->locals = p; vm->locals_cap = next; return 1;
}
void mvm_init(MVM *vm) { memset(vm, 0, sizeof(*vm)); }

static void mlist_free(MList *list) {
    if (!list || !list->items) return;
    if (heap_find(list->items)) { list->items = NULL; list->len = list->cap = 0; return; }
    for (size_t i = 0; i < list->len; ++i) mvalue_free(&list->items[i]);
    free(list->items); list->items = NULL; list->len = list->cap = 0;
}
static void mmap_free(MMap *map) {
    if (!map) return;
    if (heap_find(map->keys) || heap_find(map->values)) { map->keys = map->values = NULL; map->len = map->cap = 0; return; }
    for (size_t i = 0; i < map->len; ++i) { mvalue_free(&map->keys[i]); mvalue_free(&map->values[i]); }
    free(map->keys); free(map->values); map->keys = map->values = NULL; map->len = map->cap = 0;
}
void mvalue_free(MValue *v) {
    if (!v) return;
    if (v->tag == MVAL_LIST) mlist_free(&v->as.list);
    else if (v->tag == MVAL_MAP) mmap_free(&v->as.map);
    else if (v->tag == MVAL_STR && (v->flags & 1u) && v->as.str.ptr && !heap_find(v->as.str.ptr)) free((void *)v->as.str.ptr);
    *v = mval_none();
}
void mvm_free(MVM *vm) {
    size_t i;
    if (!vm) return;
    if (vm->tasks) {
        if (vm->current_task < vm->task_len) {
            MTask *task = &vm->tasks[vm->current_task];
            task->stack = vm->stack; task->stack_len = vm->stack_len; task->stack_cap = vm->stack_cap;
            task->frames = vm->frames; task->frame_len = vm->frame_len; task->frame_cap = vm->frame_cap;
            task->locals = vm->locals; task->locals_len = vm->locals_len; task->locals_cap = vm->locals_cap;
        }
        for (i = 0; i < vm->task_len; ++i) mellowrt_task_free_values(&vm->tasks[i]);
        free(vm->tasks);
        vm->tasks = NULL;
        vm->task_len = vm->task_cap = 0;
        vm->current_task = 0;
        vm->stack = NULL; vm->frames = NULL; vm->locals = NULL;
        vm->stack_len = vm->frame_len = vm->locals_len = 0;
        mvm_gc_collect(vm);
        memset(vm, 0, sizeof(*vm));
        return;
    }
    for (size_t i = 0; i < vm->stack_len; ++i) mvalue_free(&vm->stack[i]);
    for (size_t i = 0; i < vm->locals_len; ++i) mvalue_free(&vm->locals[i]);
    mvm_gc_collect(vm);
    free(vm->stack); free(vm->frames); free(vm->locals); memset(vm, 0, sizeof(*vm));
}
int mvm_reserve_stack(MVM *vm, size_t cap)  { return ensure_stack(vm, cap); }
int mvm_reserve_frames(MVM *vm, size_t cap) { return ensure_frames(vm, cap); }

MValue mval_none(void)  { MValue v; memset(&v,0,sizeof(v)); v.tag=MVAL_NONE; return v; }
MValue mval_bool(int x) { MValue v=mval_none(); v.tag=MVAL_BOOL; v.as.boolean=!!x; return v; }
MValue mval_i64(int64_t x) { MValue v=mval_none(); v.tag=MVAL_I64; v.as.i64=x; return v; }
MValue mval_f64(double x)  { MValue v=mval_none(); v.tag=MVAL_F64; v.as.f64=x; return v; }
MValue mval_str(const char *ptr, size_t len) { MValue v=mval_none(); v.tag=MVAL_STR; v.as.str.ptr=ptr; v.as.str.len=len; return v; }
MValue mval_func(uint32_t address, uint16_t arity, uint16_t local_count, uint16_t flags) {
    MValue v=mval_none(); v.tag=MVAL_FUNC; v.as.func.address=address; v.as.func.arity=arity;
    v.as.func.local_count=local_count; v.as.func.flags=flags; return v;
}
const char *mvalue_tag_name(MValueTag tag) {
    switch(tag){
        case MVAL_NONE:  return "none";  case MVAL_BOOL:  return "bool";
        case MVAL_I64:   return "i64";   case MVAL_F64:   return "f64";
        case MVAL_STR:   return "str";   case MVAL_BYTES: return "bytes";
        case MVAL_LIST:  return "list";  case MVAL_MAP:   return "map";
        case MVAL_FUNC:  return "func";  case MVAL_NATIVE:return "native";
        case MVAL_ERROR: return "error"; default:         return "unknown";
    }
}

/* ── owned heap string ──────────────────────────────────────────────────── */
static MValue mval_owned_str(MVM *vm, const char *src, size_t len) {
    char *buf = (char *)heap_alloc(vm, len + 1, 1, MHEAP_STR);
    MValue v = mval_none();
    if (!buf) return v;
    if (src && len) memcpy(buf, src, len);
    buf[len] = '\0';
    v.tag = MVAL_STR; v.flags = 1u; v.as.str.ptr = buf; v.as.str.len = len;
    return v;
}

/* Deep-copy a value so every allocation is independently owned by this VM. */
MValue mvalue_clone(MVM *vm, const MValue *src) {
    if (!src) return mval_none();
    switch (src->tag) {
    case MVAL_STR:
        if (src->as.str.ptr)
            return mval_owned_str(vm, src->as.str.ptr, src->as.str.len);
        return mval_none();
    case MVAL_LIST: {
        MValue v = mval_none(); v.tag = MVAL_LIST;
        v.as.list.len = v.as.list.cap = src->as.list.len;
        v.as.list.items = src->as.list.len ? (MValue*)heap_alloc(vm, src->as.list.len, sizeof(MValue), MHEAP_LIST_ITEMS) : NULL;
        if (src->as.list.len && !v.as.list.items) return mval_none();
        for (size_t i=0;i<src->as.list.len;++i)
            v.as.list.items[i] = mvalue_clone(vm, &src->as.list.items[i]);
        return v;
    }
    case MVAL_MAP: {
        MValue v = mval_none(); v.tag = MVAL_MAP;
        v.as.map.len = v.as.map.cap = src->as.map.len;
        v.as.map.keys   = src->as.map.len ? (MValue*)heap_alloc(vm, src->as.map.len, sizeof(MValue), MHEAP_MAP_KEYS) : NULL;
        v.as.map.values = src->as.map.len ? (MValue*)heap_alloc(vm, src->as.map.len, sizeof(MValue), MHEAP_MAP_VALUES) : NULL;
        if (src->as.map.len && (!v.as.map.keys||!v.as.map.values)) {
            mvalue_free(&v); return mval_none();
        }
        for (size_t i=0;i<src->as.map.len;++i) {
            v.as.map.keys[i]   = mvalue_clone(vm, &src->as.map.keys[i]);
            v.as.map.values[i] = mvalue_clone(vm, &src->as.map.values[i]);
        }
        return v;
    }
    default: return *src;
    }
}

static int truthy(MValue v) {
    switch(v.tag){
        case MVAL_NONE: return 0; case MVAL_BOOL: return v.as.boolean != 0;
        case MVAL_I64:  return v.as.i64 != 0; case MVAL_F64: return v.as.f64 != 0.0;
        case MVAL_STR:  return v.as.str.len != 0; case MVAL_LIST: return v.as.list.len != 0;
        case MVAL_MAP:  return v.as.map.len != 0; default: return 1;
    }
}
static int mvalue_is_scalar(MValue v) {
    switch (v.tag) {
        case MVAL_NONE:
        case MVAL_BOOL:
        case MVAL_I64:
        case MVAL_F64:
        case MVAL_FUNC:
        case MVAL_NATIVE:
            return 1;
        default:
            return 0;
    }
}
static void mvalue_release_temp(MValue *v) {
    if (!v) return;
    if (mvalue_is_scalar(*v)) {
        *v = mval_none();
        return;
    }
    mvalue_free(v);
}
