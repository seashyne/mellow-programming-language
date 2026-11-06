/* ── writer (Python json.dumps(indent=2, ensure_ascii=False) shape) ──────── */

static void pj_write_indent(FILE *fp, int indent) {
    int i;
    for (i = 0; i < indent; ++i) fputc(' ', fp);
}

static void pj_write_string(FILE *fp, const char *text) {
    const unsigned char *p = (const unsigned char *)(text ? text : "");
    fputc('"', fp);
    for (; *p; ++p) {
        switch (*p) {
        case '"': fputs("\\\"", fp); break;
        case '\\': fputs("\\\\", fp); break;
        case '\n': fputs("\\n", fp); break;
        case '\r': fputs("\\r", fp); break;
        case '\t': fputs("\\t", fp); break;
        case '\b': fputs("\\b", fp); break;
        case '\f': fputs("\\f", fp); break;
        default:
            if (*p < 0x20) fprintf(fp, "\\u%04x", (unsigned)*p);
            else fputc((int)*p, fp);
        }
    }
    fputc('"', fp);
}

static void pj_write_pretty(FILE *fp, const PjValue *value, int indent) {
    size_t i;
    if (!value) {
        fputs("null", fp);
        return;
    }
    switch (value->type) {
    case PJ_NULL: fputs("null", fp); break;
    case PJ_BOOL: fputs(value->boolean ? "true" : "false", fp); break;
    case PJ_NUMBER:
        if (value->number == (double)(long long)value->number)
            fprintf(fp, "%lld", (long long)value->number);
        else
            fprintf(fp, "%.17g", value->number);
        break;
    case PJ_STRING: pj_write_string(fp, value->string); break;
    case PJ_ARRAY:
        if (!value->count) {
            fputs("[]", fp);
            break;
        }
        fputs("[\n", fp);
        for (i = 0; i < value->count; ++i) {
            pj_write_indent(fp, indent + 2);
            pj_write_pretty(fp, value->items[i], indent + 2);
            if (i + 1 < value->count) fputc(',', fp);
            fputc('\n', fp);
        }
        pj_write_indent(fp, indent);
        fputc(']', fp);
        break;
    case PJ_OBJECT:
        if (!value->count) {
            fputs("{}", fp);
            break;
        }
        fputs("{\n", fp);
        for (i = 0; i < value->count; ++i) {
            pj_write_indent(fp, indent + 2);
            pj_write_string(fp, value->keys[i]);
            fputs(": ", fp);
            pj_write_pretty(fp, value->items[i], indent + 2);
            if (i + 1 < value->count) fputc(',', fp);
            fputc('\n', fp);
        }
        pj_write_indent(fp, indent);
        fputc('}', fp);
        break;
    }
}

static int pj_save(const char *path, const PjValue *value) {
    FILE *fp = fopen(path, "wb");
    if (!fp) return 0;
    pj_write_pretty(fp, value, 0);
    fputc('\n', fp);
    return fclose(fp) == 0;
}
