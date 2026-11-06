/* Pointer-indexed ownership lookup.
 *
 * Every value release and GC mark asks whether a pointer is tracked, so a
 * linear scan of g_heap_blocks made loops that churn containers quadratic
 * (money and ledger syscalls in particular). The linked list stays for sweep
 * iteration; this table only answers "is this pointer tracked?".
 */
static size_t heap_hash_ptr(const void *ptr) {
    uintptr_t key = (uintptr_t)ptr;
    key ^= key >> 17;
    key *= (uintptr_t)0x9e3779b97f4a7c15ull;
    key ^= key >> 29;
    return (size_t)key;
}

static int heap_index_grow(void) {
    size_t next = g_heap_index_cap ? g_heap_index_cap * 2 : 256;
    MHeapBlock **buckets = (MHeapBlock **)calloc(next, sizeof(*buckets));
    MHeapBlock *block;
    if (!buckets) return 0;
    for (block = g_heap_blocks; block; block = block->next) {
        size_t slot = heap_hash_ptr(block->ptr) & (next - 1);
        block->index_next = buckets[slot];
        buckets[slot] = block;
    }
    free(g_heap_index);
    g_heap_index = buckets;
    g_heap_index_cap = next;
    return 1;
}

static void heap_index_insert(MHeapBlock *block) {
    size_t slot;
    if (!g_heap_index || (g_heap_index_len + 1) * 4 > g_heap_index_cap * 3) {
        if (!heap_index_grow() && !g_heap_index_cap) return;
    }
    slot = heap_hash_ptr(block->ptr) & (g_heap_index_cap - 1);
    block->index_next = g_heap_index[slot];
    g_heap_index[slot] = block;
    g_heap_index_len++;
}

static void heap_index_remove(MHeapBlock *block) {
    MHeapBlock **cursor;
    if (!g_heap_index_cap) return;
    cursor = &g_heap_index[heap_hash_ptr(block->ptr) & (g_heap_index_cap - 1)];
    while (*cursor) {
        if (*cursor == block) {
            *cursor = block->index_next;
            g_heap_index_len--;
            return;
        }
        cursor = &(*cursor)->index_next;
    }
}

static MHeapBlock *heap_find(const void *ptr) {
    MHeapBlock *block;
    if (!ptr) return NULL;
    if (!g_heap_index_cap) {
        for (block = g_heap_blocks; block; block = block->next)
            if (block->ptr == ptr) return block;
        return NULL;
    }
    for (block = g_heap_index[heap_hash_ptr(ptr) & (g_heap_index_cap - 1)];
         block; block = block->index_next)
        if (block->ptr == ptr) return block;
    return NULL;
}
