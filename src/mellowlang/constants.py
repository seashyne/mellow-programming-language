# frinds/constants.py
# Bytecode opcodes for MellowLangVM (Sandbox-first, v2.2)

class Op:
    HALT      = 0   # Stop VM execution immediately

    PUSH      = 1   # Push constant onto stack
    STORE     = 2   # Store stack top into variable (current scope)
    STORE_KEEP = 40  # Store stack top into persistent keep store (and current scope)
    STORE_AUTO = 41  # Store stack top into variable; if name exists in keep store, update it too
    LOAD      = 3   # Load variable onto stack (search local -> global)

    ADD       = 4
    SUB       = 5
    MUL       = 6
    DIV       = 7

    # COMPARE takes an operator string as operand: '==','!=','>','<','>=','<='
    COMPARE   = 8

    PRINT     = 9

    # v1.2.5: multi-value print/show (prints N values space-separated)
    PRINTN    = 44

    JUMP      = 10
    JIF       = 11

    # CALL takes (name, argc)
    CALL      = 12
    RETURN    = 13
    ARG       = 14

    SHOW_PREC = 15

    ASK       = 16
    RANDOM    = 17

    STOP      = 18  # Stop program

    WAIT      = 19

    # Storage
    SAVE      = 23      # bytecode: SAVE var_name (filename on stack)
    LOAD_F    = 24      # LOAD_F var_name (filename on stack)
    SAVE_VAL  = 32      # SAVE_VAL (stack: filename, value)

    # List helpers
    LIST_HAS  = 25
    LIST_PUT  = 26      # (stack: item, list)

    # Boolean ops
    BOOL_AND  = 27
    BOOL_OR   = 28
    BOOL_NOT  = 29

    # Host bridge
    SYSCALL   = 30      # SYSCALL argc (stack: name, arg1..argN)

    POP       = 31      # discard stack top

    # Collection helpers
    GETITEM   = 33      # (stack: container, index) -> value
    LEN       = 34      # (stack: container) -> length

    BUILD_LIST = 35     # BUILD_LIST n (pop n items) -> list
    BUILD_MAP  = 36     # BUILD_MAP n (pop 2n items k,v) -> dict

    # Error handling
    TRY       = 37     # TRY catch_pc finally_pc err_name
    ENDTRY    = 38     # ENDTRY

    RANDFLOAT = 39     # random float [0,1)

    SEED      = 42     # seed deterministic RNG (stack: seed)

    GLOBAL_SEED = 43   # set global base seed (stack: seed). VM derives per-script seed from it.

    # v1.4.9: First-class functions
    PUSH_FUNC = 45     # PUSH_FUNC name  -> push function reference onto stack
    CALL_VAL  = 46     # CALL_VAL argc  -> pop func ref + argc args, call it

    # v1.4.9: Slicing  
    SLICE     = 47     # SLICE  (stack: target, start_or_None, stop_or_None) -> sliced

    # v1.4.9: Module import
    IMPORT    = 49     # IMPORT path alias  -> load .mellow file and bind namespace

    # v1.4.9: Modulo operator
    MOD       = 50     # stack: a, b -> a % b

    # v1.4.9: Power operator
    POW_OP    = 51     # stack: a, b -> a ** b
