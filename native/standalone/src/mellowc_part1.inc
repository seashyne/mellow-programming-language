void set_error(Compiler *c, const char *message) {
    if (c->error && c->error_cap && !c->error[0])
        snprintf(c->error, c->error_cap, "%s:%d:1: syntax error: %s",
                 c->source_name ? c->source_name : "<memory>", c->current_line, message);
}

char *copy_text(const char *s, size_t n) {
    char *p = (char *)calloc(n + 1, 1);
    if (p && n) memcpy(p, s, n);
    return p;
}

static int reserve(void **ptr, size_t *cap, size_t need, size_t item_size) {
    size_t next;
    void *grown;
    if (*cap >= need) return 1;
    next = *cap ? *cap * 2 : 32;
    while (next < need) next *= 2;
    grown = realloc(*ptr, next * item_size);
    if (!grown) return 0;
    *ptr = grown;
    *cap = next;
    return 1;
}

int emit(Compiler *c, int op, int a, int b, int d) {
    MSourceSpan span;
    if (!reserve((void **)&c->code, &c->code_cap, c->code_len + 1, sizeof(*c->code)) ||
        !reserve((void **)&c->spans, &c->span_cap, c->span_len + 1, sizeof(*c->spans))) {
        set_error(c, "out of memory");
        return -1;
    }
    c->code[c->code_len] = (MInstruction){(uint8_t)op, a, b, d};
    span = (MSourceSpan){(uint32_t)c->current_line, 1, (uint32_t)c->current_line, 1};
    c->spans[c->span_len++] = span;
    return (int)c->code_len++;
}

int add_const(Compiler *c, MValue value) {
    if (!reserve((void **)&c->consts, &c->const_cap, c->const_len + 1, sizeof(*c->consts))) {
        set_error(c, "constant pool allocation failed");
        return -1;
    }
    c->consts[c->const_len] = value;
    return (int)c->const_len++;
}

MValue owned_string(const char *s, size_t n) {
    MValue value = mval_none();
    char *copy = copy_text(s, n);
    if (!copy) return value;
    value.tag = MVAL_STR;
    value.flags = 1u;
    value.as.str.ptr = copy;
    value.as.str.len = n;
    return value;
}

int scope_find(Scope *scope, const char *name, size_t len) {
    int i;
    for (i = 0; i < scope->len; ++i)
        if (strlen(scope->vars[i].name) == len && memcmp(scope->vars[i].name, name, len) == 0)
            return scope->vars[i].slot;
    return -1;
}

int scope_slot(Scope *scope, const char *name, size_t len, int create) {
    int slot = scope_find(scope, name, len);
    if (slot >= 0 || !create || scope->len >= 256) return slot;
    slot = scope->len;
    snprintf(scope->vars[scope->len].name, sizeof(scope->vars[scope->len].name), "%.*s", (int)len, name);
    scope->vars[scope->len].slot = slot;
    scope->is_i64[scope->len] = 0;
    scope->i64_list_len[scope->len] = 0;
    scope->len++;
    return slot;
}

Function *find_function(Compiler *c, const char *name, size_t len) {
    int i;
    for (i = 0; i < c->func_count; ++i)
        if (strlen(c->funcs[i].name) == len && memcmp(c->funcs[i].name, name, len) == 0)
            return &c->funcs[i];
    return NULL;
}

const char *trim(char *text) {
    while (*text && isspace((unsigned char)*text)) text++;
    return text;
}

void strip_inline_comment(char *text) {
    int quote = 0;
    int escaped = 0;
    int depth = 0;
    size_t i;
    for (i = 0; text[i]; ++i) {
        char ch = text[i];
        if (escaped) { escaped = 0; continue; }
        if (quote) {
            if (ch == '\\') escaped = 1;
            else if (ch == quote) quote = 0;
            continue;
        }
        if (ch == '"' || ch == '\'') { quote = ch; continue; }
        if (ch == '(' || ch == '[' || ch == '{') depth++;
        else if ((ch == ')' || ch == ']' || ch == '}') && depth > 0) depth--;
        else if (depth == 0 && ch == '#') { text[i] = '\0'; break; }
        else if (depth == 0 && ch == '/' && text[i + 1] == '/') { text[i] = '\0'; break; }
    }
    while (i > 0 && isspace((unsigned char)text[i - 1])) text[--i] = '\0';
}

int starts(const char *text, const char *prefix) {
    size_t n = strlen(prefix);
    return strncmp(text, prefix, n) == 0;
}

static int ident_len_at(const char *text) {
    int n = 0;
    if (!text || !(isalpha((unsigned char)text[0]) || text[0] == '_')) return 0;
    while (isalnum((unsigned char)text[n]) || text[n] == '_') n++;
    return n;
}

static const char *skip_spaces(const char *text) {
    while (*text && isspace((unsigned char)*text)) text++;
    return text;
}

/* File-static loop-shape recognizers; included here so mellowc.c stays their
 * only translation unit. */
#include "mellowc_fastloops.inc"

int find_assignment(const char *text) {
    int depth=0, quote=0, i;
    for(i=0;text[i];++i) {
        char ch=text[i];
        if(quote){if(ch==quote&&text[i-1]!='\\')quote=0;continue;}
        if(ch=='"'||ch=='\''){quote=ch;continue;}
        if(ch=='('||ch=='['||ch=='{')depth++;
        else if(ch==')'||ch==']'||ch=='}')depth--;
        else if(ch=='='&&depth==0&&text[i+1]!='='&&
                (i==0||(text[i-1]!='!'&&text[i-1]!='<'&&text[i-1]!='>')))return i;
    }
    return -1;
}

static int compile_block(Compiler *c, int *position, int end, int indent);

