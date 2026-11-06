static char *read_text_file(const char *path) {
    FILE *f;
    long size;
    char *source;
    if (!path) return NULL;
    f = fopen(path, "rb");
    if (!f) return NULL;
    if (fseek(f, 0, SEEK_END) != 0) { fclose(f); return NULL; }
    size = ftell(f);
    if (size < 0) { fclose(f); return NULL; }
    if (fseek(f, 0, SEEK_SET) != 0) { fclose(f); return NULL; }
    source = (char *)calloc((size_t)size + 1u, 1u);
    if (!source) { fclose(f); return NULL; }
    if (fread(source, 1, (size_t)size, f) != (size_t)size) {
        free(source);
        fclose(f);
        return NULL;
    }
    fclose(f);
    return source;
}

static int path_already_imported(char imported[][1024], int imported_count, const char *path) {
    int i;
    for (i = 0; i < imported_count; ++i)
        if (strcmp(imported[i], path) == 0) return 1;
    return 0;
}

static int append_text(char **out, size_t *len, size_t *cap, const char *text) {
    size_t n = strlen(text);
    char *grown;
    if (*len + n + 2u > *cap) {
        size_t next = *cap ? *cap * 2u : 4096u;
        while (*len + n + 2u > next) next *= 2u;
        grown = (char *)realloc(*out, next);
        if (!grown) return 0;
        *out = grown;
        *cap = next;
    }
    memcpy(*out + *len, text, n);
    *len += n;
    if (*len == 0 || (*out)[*len - 1] != '\n') (*out)[(*len)++] = '\n';
    (*out)[*len] = '\0';
    return 1;
}

static int expand_package_imports_into(
    const char *source,
    const char *source_name,
    int depth,
    char imported[][1024],
    int *imported_count,
    char **out,
    size_t *out_len,
    size_t *out_cap
) {
    const char *p = source;
    const char *start = source;
    if (depth > 8) return 1;
    while (1) {
        if (*p == '\n' || *p == '\0') {
            size_t n = (size_t)(p - start);
            char line[512];
            char module[128];
            if (n >= sizeof(line)) n = sizeof(line) - 1;
            memcpy(line, start, n);
            line[n] = '\0';
            if (parse_import_module_name(line, module, sizeof(module)) && !line_module_is_builtin(module)) {
                char resolved[1024];
                if (mellowrt_resolve_package_entry(source_name, module, resolved, sizeof(resolved)) &&
                    !path_already_imported(imported, *imported_count, resolved) &&
                    *imported_count < 32) {
                    char *pkg_source;
                    snprintf(imported[*imported_count], 1024, "%s", resolved);
                    (*imported_count)++;
                    pkg_source = read_text_file(resolved);
                    if (pkg_source) {
                        if (!expand_package_imports_into(pkg_source, resolved, depth + 1, imported, imported_count, out, out_len, out_cap)) {
                            free(pkg_source);
                            return 0;
                        }
                        free(pkg_source);
                    }
                }
            }
            if (*p == '\0') break;
            start = p + 1;
        }
        p++;
    }
    return append_text(out, out_len, out_cap, source);
}

static char *expand_package_imports(const char *source, const char *source_name) {
    char imported[32][1024];
    int imported_count = 0;
    char *out = NULL;
    size_t out_len = 0, out_cap = 0;
    memset(imported, 0, sizeof(imported));
    if (!expand_package_imports_into(source, source_name, 0, imported, &imported_count, &out, &out_len, &out_cap)) {
        free(out);
        return NULL;
    }
    return out;
}

static int scan_functions(Compiler *c) {
    int i;
    for(i=0;i<c->line_count;++i){
        char *text=(char*)trim(c->lines[i].text);
        if(c->lines[i].indent==0&&starts(text,"def ")){
            Function *fn;
            char *lp=strchr(text,'('),*rp=strrchr(text,')'),*cursor;
            int j=i+1;
            if(!lp||!rp||rp<lp||c->func_count>=128){c->current_line=c->lines[i].number;set_error(c,"invalid function declaration");return 0;}
            fn=&c->funcs[c->func_count++];memset(fn,0,sizeof(*fn));
            snprintf(fn->name,sizeof(fn->name),"%.*s",(int)(lp-(text+4)),text+4);
            cursor=lp+1;
            while(cursor<rp){
                char *comma=strchr(cursor,',');char *stop=comma&&comma<rp?comma:rp;
                while(cursor<stop&&isspace((unsigned char)*cursor))cursor++;
                while(stop>cursor&&isspace((unsigned char)stop[-1]))stop--;
                if(stop>cursor){
                    if(fn->arity>=16){c->current_line=c->lines[i].number;set_error(c,"function has more than 16 parameters");return 0;}
                    snprintf(fn->params[fn->arity++],64,"%.*s",(int)(stop-cursor),cursor);
                }
                cursor=comma&&comma<rp?comma+1:rp;
            }
            while(j<c->line_count&&(c->lines[j].indent>0||!*trim(c->lines[j].text)))j++;
            fn->line_start=i;fn->line_end=j;fn->body_indent=4;
            fn->const_slot=add_const(c,mval_func(0,(uint16_t)fn->arity,0,0));
        }
    }
    return 1;
}

int mellow_compile_source(const char *source,const char *source_name,MNativeProgram *out,char *error,size_t error_cap){
    Compiler c;int i,pos,jump_main;
    char *expanded_source = NULL;
    memset(&c,0,sizeof(c));memset(out,0,sizeof(*out));
    c.error=error;c.error_cap=error_cap;c.scope=&c.globals;c.current_line=1;c.source_name=source_name;
    if(error&&error_cap)error[0]='\0';
    expanded_source = expand_package_imports(source, source_name ? source_name : "<memory>");
    if(!expanded_source){set_error(&c,"package import expansion failed");goto fail;}
    if(!split_lines(&c,expanded_source)||!scan_functions(&c))goto fail;
    jump_main=emit(&c,MOP_JUMP,0,0,0);
    for(i=0;i<c.func_count;++i){
        Scope local;Function *fn=&c.funcs[i];memset(&local,0,sizeof(local));
        for(int p=0;p<fn->arity;++p)scope_slot(&local,fn->params[p],strlen(fn->params[p]),1);
        c.scope=&local;fn->address=(int)c.code_len;pos=fn->line_start+1;
        if(!compile_block(&c,&pos,fn->line_end,fn->body_indent))goto fail;
        if(!c.code_len||c.code[c.code_len-1].opcode!=MOP_RETURN){
            int none=add_const(&c,mval_none());emit(&c,MOP_PUSH_CONST,none,0,0);emit(&c,MOP_RETURN,0,0,0);
        }
        fn->local_count=local.len;
        c.consts[fn->const_slot]=mval_func((uint32_t)fn->address,(uint16_t)fn->arity,(uint16_t)fn->local_count,0);
    }
    c.scope=&c.globals;c.code[jump_main].a=(int32_t)c.code_len;pos=0;
    if(!compile_block(&c,&pos,c.line_count,0))goto fail;
    emit(&c,MOP_HALT,0,0,0);
    out->code=c.code;out->code_len=c.code_len;out->consts=c.consts;out->const_len=c.const_len;
    out->spans=c.spans;out->span_len=c.span_len;out->source_name=copy_text(source_name?source_name:"<memory>",strlen(source_name?source_name:"<memory>"));
    for(i=0;i<c.line_count;++i)free(c.lines[i].text);
    free(c.lines);
    free(expanded_source);
    return 1;
fail:
    for(i=0;i<c.line_count;++i)free(c.lines[i].text);
    free(c.lines);
    for(i=0;i<(int)c.const_len;++i)mvalue_free(&c.consts[i]);
    free(c.consts);free(c.code);free(c.spans);
    free(expanded_source);
    return 0;
}

int mellow_compile_file(const char *path,MNativeProgram *out,char *error,size_t error_cap){
    FILE *f=fopen(path,"rb");long size;char *source;int ok;
    if(!f){if(error&&error_cap)snprintf(error,error_cap,"cannot open %s",path);return 0;}
    fseek(f,0,SEEK_END);size=ftell(f);fseek(f,0,SEEK_SET);
    source=(char*)calloc((size_t)size+1,1);
    if(!source||fread(source,1,(size_t)size,f)!=(size_t)size){free(source);fclose(f);return 0;}
    fclose(f);ok=mellow_compile_source(source,path,out,error,error_cap);free(source);return ok;
}

void mellow_native_program_free(MNativeProgram *program){
    size_t i;if(!program)return;
    for(i=0;i<program->const_len;++i)mvalue_free(&program->consts[i]);
    free(program->consts);free(program->code);free(program->spans);free(program->source_name);
    memset(program,0,sizeof(*program));
}
