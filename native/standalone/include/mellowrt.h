#ifndef MELLOWRT_H
#define MELLOWRT_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    MVAL_NONE = 0,
    MVAL_BOOL = 1,
    MVAL_I64 = 2,
    MVAL_F64 = 3,
    MVAL_STR = 4,
    MVAL_BYTES = 5,
    MVAL_LIST = 6,
    MVAL_MAP = 7,
    MVAL_FUNC = 8,
    MVAL_NATIVE = 9,
    MVAL_ERROR = 10
} MValueTag;

typedef struct {
    const char *ptr;
    size_t len;
} MStringView;

typedef struct MValue MValue;

typedef struct {
    MValue *items;
    size_t len;
    size_t cap;
} MList;

typedef struct {
    MValue *keys;
    MValue *values;
    size_t len;
    size_t cap;
} MMap;

typedef struct {
    uint32_t address;
    uint16_t arity;
    uint16_t local_count;
    uint16_t flags;
} MFunctionRef;

struct MValue {
    MValueTag tag;
    uint32_t flags;
    union {
        int64_t i64;
        double f64;
        int boolean;
        MStringView str;
        MList list;
        MMap map;
        MFunctionRef func;
        void *ptr;
    } as;
};

typedef enum {
    MOP_HALT = 0,
    MOP_PUSH_CONST = 1,
    MOP_LOAD_LOCAL = 2,
    MOP_STORE_LOCAL = 3,
    MOP_ADD = 4,
    MOP_SUB = 5,
    MOP_MUL = 6,
    MOP_DIV = 7,
    MOP_JUMP = 8,
    MOP_JUMP_IF_FALSE = 9,
    MOP_CALL = 10,
    MOP_RETURN = 11,
    MOP_POP = 12,
    MOP_COMPARE = 13,
    MOP_BUILD_LIST = 14,
    MOP_BUILD_MAP = 15,
    MOP_IMPORT = 16,
    MOP_SYSCALL = 17,
    MOP_DEBUG_SNAPSHOT = 18,
    MOP_DUP = 19,
    /* v2.3.4 extended surface */
    MOP_MOD = 20,
    MOP_POW = 21,
    MOP_BOOL_AND = 22,
    MOP_BOOL_OR = 23,
    MOP_BOOL_NOT = 24,
    MOP_GETITEM = 25,
    MOP_LEN = 26,
    MOP_PUSH_FUNC = 27,
    MOP_CALL_VAL = 28,
    MOP_STOP = 29
} MOpcode;

typedef enum {
    MCMP_EQ = 0,
    MCMP_NE = 1,
    MCMP_LT = 2,
    MCMP_LE = 3,
    MCMP_GT = 4,
    MCMP_GE = 5
} MCompareOp;

typedef struct {
    uint8_t opcode;
    int32_t a;
    int32_t b;
    int32_t c;
} MInstruction;

typedef struct {
    uint32_t start_line;
    uint32_t start_col;
    uint32_t end_line;
    uint32_t end_col;
} MSourceSpan;

typedef struct {
    uint32_t frame_id;
    uint32_t return_pc;
    uint32_t base;
    uint32_t local_base;
    uint32_t local_count;
    MFunctionRef function;
} MFrame;

typedef struct {
    uint64_t id;
    uint32_t pc;
    int active;
    int finished;
    int blocked;
    void *waiting_native;
    MValue result;
    MValue *stack;
    size_t stack_len;
    size_t stack_cap;
    MFrame *frames;
    size_t frame_len;
    size_t frame_cap;
    MValue *locals;
    size_t locals_len;
    size_t locals_cap;
} MTask;

typedef struct {
    const MInstruction *code;
    size_t code_len;
    const MValue *const_pool;
    size_t const_len;
    const MSourceSpan *span_map;
    size_t span_len;
    const char *source_name;
} MProgram;

typedef struct {
    uint64_t executed_instructions;
    uint64_t allocations;
    uint64_t syscalls;
    int halted;
    int failed;
    MValue result;
    const char *error_message;
    uint32_t error_pc;
    MSourceSpan error_span;
    int has_error_span;
} MRunResult;

typedef struct {
    const char *architecture;
    const char *backend;
    uint32_t pointer_bits;
    int little_endian;
    int arm_neon_available;
    int optimized_kernels;
} MRuntimePlatform;

typedef struct {
    uint32_t pc;
    const MInstruction *insn;
    const MSourceSpan *span;
    const MFrame *frame;
    const MFrame *frames;
    size_t frame_len;
    const MValue *stack;
    size_t stack_len;
    const MValue *locals;
    size_t locals_len;
} MDebugSnapshot;

typedef int (*MDebugHook)(void *user, const MDebugSnapshot *snapshot);
typedef int (*MSyscallHandler)(void *user, int32_t syscall_id, const MValue *args, size_t argc, MValue *out_result);

typedef struct {
    MDebugHook on_before_instruction;
    MDebugHook on_after_instruction;
    void *user;
} MDebugHooks;

typedef struct {
    MSyscallHandler fn;
    void *user;
} MSyscallBridge;

typedef struct {
    MValue *stack;
    size_t stack_len;
    size_t stack_cap;
    MFrame *frames;
    size_t frame_len;
    size_t frame_cap;
    MValue *locals;
    size_t locals_len;
    size_t locals_cap;
    MDebugHooks debug;
    MSyscallBridge syscall;
    uint64_t heap_allocated;
    uint64_t heap_freed;
    uint64_t heap_live;
    uint64_t heap_blocks;
    uint64_t heap_bytes;
    uint64_t heap_last_gc_freed;
    uint64_t heap_last_gc_freed_bytes;
    MTask *tasks;
    size_t task_len;
    size_t task_cap;
    size_t current_task;
    uint64_t next_task_id;
} MVM;

typedef struct {
    MInstruction *code;
    size_t code_len;
    MValue *consts;
    size_t const_len;
    MSourceSpan *spans;
    size_t span_len;
    char *source_name;
} MNativeProgram;

void mvm_init(MVM *vm);
void mvm_free(MVM *vm);
int mvm_reserve_stack(MVM *vm, size_t cap);
int mvm_reserve_frames(MVM *vm, size_t cap);
int mvm_reserve_locals(MVM *vm, size_t cap);
int mvm_run(MVM *vm, const MProgram *program, MRunResult *out);
MRuntimePlatform mellow_runtime_platform(void);

MValue mval_none(void);
MValue mval_bool(int v);
MValue mval_i64(int64_t v);
MValue mval_f64(double v);
MValue mval_str(const char *ptr, size_t len);
MValue mval_func(uint32_t address, uint16_t arity, uint16_t local_count, uint16_t flags);
const char *mvalue_tag_name(MValueTag tag);
void mvalue_free(MValue *v);
MValue mvalue_clone(MVM *vm, const MValue *src);
void mvm_gc_mark_value(MVM *vm, const MValue *value);
uint64_t mvm_gc_collect(MVM *vm);
uint64_t mvm_gc_collect_with_marker(MVM *vm, void (*marker)(void *user, MVM *vm), void *user);

int mellow_compile_source(const char *source, const char *source_name, MNativeProgram *out, char *error, size_t error_cap);
int mellow_compile_file(const char *path, MNativeProgram *out, char *error, size_t error_cap);
void mellow_native_program_free(MNativeProgram *program);

#ifdef __cplusplus
}
#endif

#endif
