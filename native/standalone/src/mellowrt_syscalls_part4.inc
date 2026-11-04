    case 63:
    case 64:
    case 65:
    case 66:
    case 67:
    case 68:
    case 69:
    case 70:
    case 71:
    case 72:
    case 73:
    case 74:
    case 75:
    case 76:
    case 77:
    case 78:
        return mellowrt_storage_syscall(id,args,argc,out_result,
                                        ctx?ctx->storage_dir:NULL,
                                        ctx?sizeof(ctx->storage_dir):0,
                                        ctx?ctx->syscall_error:NULL,
                                        ctx?sizeof(ctx->syscall_error):0);
    default: return 0;
    }
}
