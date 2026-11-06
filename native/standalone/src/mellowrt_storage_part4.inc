    case 63: { /* storage_info */
        MValue info = mval_none();
        if (argc != 0) return 0;
        info.tag = MVAL_MAP;
        info.as.map.keys = (MValue *)calloc(2, sizeof(MValue));
        info.as.map.values = (MValue *)calloc(2, sizeof(MValue));
        if (!info.as.map.keys || !info.as.map.values) {
            free(info.as.map.keys);
            free(info.as.map.values);
            return 0;
        }
        info.as.map.len = info.as.map.cap = 2;
        absolute_path(base, path, sizeof path);
        info.as.map.keys[0] = owned_text("storage_dir");
        info.as.map.values[0] = owned_text(base);
        info.as.map.keys[1] = owned_text("storage_abs");
        info.as.map.values[1] = owned_text(path);
        *out_result = info;
        return 1;
    }
    case 64: { /* save_data */
        MValue key = arg_at(args, argc, 0);
        MValue value = arg_at(args, argc, 1);
        MValue swap;
        if (argc < 2) return 0;
        /* save_data accepts (key, value) or (value, key), like the Python VM */
        if (key.tag != MVAL_STR && value.tag == MVAL_STR) { swap = key; key = value; value = swap; }
        if (!storage_write_slot(base, &key, &value, error, error_cap)) return 0;
        *out_result = mval_bool(1);
        return 1;
    }
    case 65: /* load_data */
        if (argc < 1) return 0;
        if (!storage_read_slot(base, arg_ptr(args, argc, 0), out_result, error, error_cap)) return 0;
        return 1;
    case 66: { /* storage.mkdir under the storage base */
        path_clean(arg_ptr(args, argc, 0), clean, sizeof clean);
        if (argc > 1) return 0;
        if (!join_under_base(path, sizeof path, base, clean)) {
            set_error(error, error_cap, ERR_FILE_TRAVERSAL);
            return 0;
        }
        make_dirs(path);
        *out_result = mval_bool(file_exists(path));
        return 1;
    }
    default:
        break;
    }

    if (id >= 67 && id <= 73) {
        if (id == 73) { /* fs_pwd */
            char cwd[STOR_PATH_MAX];
            if (argc != 0) return 0;
            if (STOR_GET_CWD(cwd, sizeof cwd) == NULL) return 0;
            *out_result = owned_text(cwd);
            return 1;
        }
        if (!fs_host_path(arg_ptr(args, argc, 0), path, sizeof path, error, error_cap)) return 0;
        switch (id) {
        case 67: /* fs_read */
            if (!storage_read_text(path, out_result, error, error_cap)) return 0;
            return 1;
        case 68: /* fs_write */
        case 69: /* fs_append */
            if (!storage_write_text(path, arg_ptr(args, argc, 1), id == 69, 1, error, error_cap)) return 0;
            *out_result = mval_bool(1);
            return 1;
        case 70: /* fs_exists */
            *out_result = mval_bool(file_exists(path));
            return 1;
        case 71: /* fs_delete */
            if (!file_exists(path)) { *out_result = mval_bool(0); return 1; }
            *out_result = mval_bool(remove(path) == 0);
            return 1;
        default: /* 72: fs_mkdir */
            make_dirs(path);
            *out_result = mval_bool(file_exists(path));
            return 1;
        }
    }

    if (id >= 74 && id <= 78) {
        /* file_* stays under the storage base, like the Python sandbox does. */
        path_clean(arg_ptr(args, argc, 0), clean, sizeof clean);
        if (!join_under_base(path, sizeof path, base, clean)) {
            set_error(error, error_cap, ERR_FILE_TRAVERSAL);
            return 0;
        }
        switch (id) {
        case 74: /* file_read */
            if (!storage_read_text(path, out_result, error, error_cap)) return 0;
            return 1;
        case 75: /* file_write */
        case 76: /* file_append */
            if (!file_exists(base)) make_dirs(base);
            if (!storage_write_text(path, arg_ptr(args, argc, 1), id == 76, 0, error, error_cap)) return 0;
            *out_result = mval_bool(1);
            return 1;
        case 77: /* file_exists */
            *out_result = mval_bool(file_exists(path));
            return 1;
        default: /* 78: file_delete */
            if (!file_exists(path)) { *out_result = mval_bool(0); return 1; }
            *out_result = mval_bool(remove(path) == 0);
            return 1;
        }
    }

    return 0;
}
