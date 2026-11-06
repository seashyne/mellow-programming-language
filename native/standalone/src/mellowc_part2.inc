static int compile_statement(Compiler *c, int *position, int end, int indent) {
    SourceLine *line=&c->lines[*position];
    char *text=(char*)trim(line->text);
    int assign;
    c->current_line=line->number;
    strip_inline_comment(text);
    text=(char*)trim(text);
    if (!*text || starts(text,"//") || *text=='#') { (*position)++; return 1; }
    {
        int import_result = parse_import_statement(c, text);
        if (import_result < 0) return 0;
        if (import_result > 0) { (*position)++; return 1; }
    }
    if (starts(text,"def ")) {
        Function *fn=NULL; int i;
        for(i=0;i<c->func_count;++i)if(c->funcs[i].line_start==*position){fn=&c->funcs[i];break;}
        *position=fn?fn->line_end:*position+1;
        return 1;
    }
    if (starts(text,"if ") && text[strlen(text)-1]==':') {
        int jump_false;
        int end_jumps[32];
        int end_count=0;
        text[strlen(text)-1]='\0';
        if(!compile_expr(c,text+3))return 0;
        jump_false=emit(c,MOP_JUMP_IF_FALSE,0,0,0);
        (*position)++;
        if(!compile_block(c,position,end,indent+4))return 0;
        while(*position<end && c->lines[*position].indent==indent){
            char *next=(char*)trim(c->lines[*position].text);
            strip_inline_comment(next);
            next=(char*)trim(next);
            if(starts(next,"elif ") && next[strlen(next)-1]==':'){
                if(end_count<32)end_jumps[end_count++]=emit(c,MOP_JUMP,0,0,0);
                c->code[jump_false].a=(int32_t)c->code_len;
                next[strlen(next)-1]='\0';
                c->current_line=c->lines[*position].number;
                if(!compile_expr(c,next+5))return 0;
                jump_false=emit(c,MOP_JUMP_IF_FALSE,0,0,0);
                (*position)++;
                if(!compile_block(c,position,end,indent+4))return 0;
                continue;
            }
            if(starts(next,"else:")){
                if(end_count<32)end_jumps[end_count++]=emit(c,MOP_JUMP,0,0,0);
                c->code[jump_false].a=(int32_t)c->code_len;
                c->current_line=c->lines[*position].number;
                (*position)++;
                if(!compile_block(c,position,end,indent+4))return 0;
                jump_false=-1;
            }
            break;
        }
        if(jump_false>=0)c->code[jump_false].a=(int32_t)c->code_len;
        for(int j=0;j<end_count;++j)c->code[end_jumps[j]].a=(int32_t)c->code_len;
        return 1;
    }
    if (starts(text,"stop")) {
        emit(c,MOP_STOP,0,0,0);(*position)++;return 1;
    }
    if (starts(text,"show ")) {
        if(!compile_expr(c,trim(text+5)))return 0;
        emit(c,MOP_SYSCALL,1,1,0);
        (*position)++;return 1;
    }
    if (starts(text,"while ") && text[strlen(text)-1]==':') {
        int loop, jf, depth, fast_loop;
        text[strlen(text)-1]='\0';
        fast_loop = emit_fast_i64_branch_mod2_loop(c, position, end, indent, trim(text+6));
        if (fast_loop < 0) return 0;
        if (fast_loop) return 1;
        fast_loop = emit_fast_i64_list_mod_loop(c, position, end, indent, trim(text+6));
        if (fast_loop < 0) return 0;
        if (fast_loop) return 1;
        fast_loop = emit_fast_i64_add_func_loop(c, position, end, indent, trim(text+6));
        if (fast_loop < 0) return 0;
        if (fast_loop) return 1;
        fast_loop = emit_fast_string_append_loop(c, position, end, indent, trim(text+6));
        if (fast_loop < 0) return 0;
        if (fast_loop) return 1;
        fast_loop = emit_fast_i64_sum_loop(c, position, end, indent, trim(text+6));
        if (fast_loop < 0) return 0;
        if (fast_loop) return 1;
        loop=(int)c->code_len;
        depth=c->loop_depth++;
        c->loop_break_count[depth]=0;
        c->loop_continue_count[depth]=0;
        {
            int fast_condition = emit_fast_i64_lt_jump(c, trim(text+6), &jf);
            if (fast_condition < 0) return 0;
            if (!fast_condition) {
                if(!compile_expr(c,text+6))return 0;
                jf=emit(c,MOP_JUMP_IF_FALSE,0,0,0);
            }
        }
        (*position)++;
        if(!compile_block(c,position,end,indent+4))return 0;
        for(int j=0;j<c->loop_continue_count[depth];++j)c->code[c->loop_continues[depth][j]].a=loop;
        emit(c,MOP_JUMP,loop,0,0);
        if (c->code[jf].opcode == MOP_JUMP_IF_LOCAL_I64_LT_FALSE) c->code[jf].c=(int32_t)c->code_len;
        else c->code[jf].a=(int32_t)c->code_len;
        for(int j=0;j<c->loop_break_count[depth];++j)c->code[c->loop_breaks[depth][j]].a=(int32_t)c->code_len;
        c->loop_depth--;
        return 1;
    }
    if (starts(text,"for ") && text[strlen(text)-1]==':') {
        char name[64], start_expr[256], stop_expr[256];
        int slot, stop_slot, loop, jf;
        int depth=c->loop_depth++;
        c->loop_break_count[depth]=0;
        c->loop_continue_count[depth]=0;
        if(sscanf(text,"for %63s in range(%255[^,],%255[^)]):",name,start_expr,stop_expr)!=3){
            if(sscanf(text,"for %63s in range(%255[^)]):",name,stop_expr)!=2){
                set_error(c,"expected for name in range(start, stop):");return 0;
            }
            snprintf(start_expr,sizeof(start_expr),"0");
        }
        slot=scope_slot(c->scope,name,strlen(name),1);
        snprintf(name,sizeof(name),"__stop_%d",line->number);
        stop_slot=scope_slot(c->scope,name,strlen(name),1);
        if(!compile_expr(c,start_expr)||emit(c,MOP_STORE_LOCAL,slot,0,0)<0||
           !compile_expr(c,stop_expr)||emit(c,MOP_STORE_LOCAL,stop_slot,0,0)<0)return 0;
        loop=(int)c->code_len;
        emit(c,MOP_LOAD_LOCAL,slot,0,0);emit(c,MOP_LOAD_LOCAL,stop_slot,0,0);emit(c,MOP_COMPARE,MCMP_LT,0,0);
        jf=emit(c,MOP_JUMP_IF_FALSE,0,0,0);
        (*position)++;
        if(!compile_block(c,position,end,indent+4))return 0;
        for(int j=0;j<c->loop_continue_count[depth];++j)c->code[c->loop_continues[depth][j]].a=(int32_t)c->code_len;
        emit(c,MOP_LOAD_LOCAL,slot,0,0);
        {int one=add_const(c,mval_i64(1));emit(c,MOP_PUSH_CONST,one,0,0);}
        emit(c,MOP_ADD,0,0,0);emit(c,MOP_STORE_LOCAL,slot,0,0);emit(c,MOP_JUMP,loop,0,0);
        c->code[jf].a=(int32_t)c->code_len;
        for(int j=0;j<c->loop_break_count[depth];++j)c->code[c->loop_breaks[depth][j]].a=(int32_t)c->code_len;
        c->loop_depth--;
        return 1;
    }
    if (starts(text,"break")) {
        int depth=c->loop_depth-1;
        int jump;
        if(depth<0){set_error(c,"break outside loop");return 0;}
        jump=emit(c,MOP_JUMP,0,0,0);
        if(c->loop_break_count[depth]<64)c->loop_breaks[depth][c->loop_break_count[depth]++]=jump;
        (*position)++;return 1;
    }
    if (starts(text,"continue")) {
        int depth=c->loop_depth-1;
        int jump;
        if(depth<0){set_error(c,"continue outside loop");return 0;}
        jump=emit(c,MOP_JUMP,0,0,0);
        if(c->loop_continue_count[depth]<64)c->loop_continues[depth][c->loop_continue_count[depth]++]=jump;
        (*position)++;return 1;
    }
    if (starts(text,"wait ")) {
        char *expr=(char*)trim(text+5);
        char *endp=NULL;
        double seconds=strtod(expr,&endp);
        if(endp&&*trim(endp)=='\0'){
            int ci=add_const(c,mval_i64((int64_t)(seconds*1000.0)));
            if(ci<0||emit(c,MOP_PUSH_CONST,ci,0,0)<0)return 0;
        } else {
            if(!compile_expr(c,expr))return 0;
        }
        emit(c,MOP_SYSCALL,18,1,0);
        (*position)++;return 1;
    }
    if (starts(text,"return")) {
        const char *expr=trim(text+6);
        if(*expr){if(!compile_expr(c,expr))return 0;}
        else {int ci=add_const(c,mval_none());emit(c,MOP_PUSH_CONST,ci,0,0);}
        emit(c,MOP_RETURN,0,0,0);(*position)++;return 1;
    }
    if (starts(text,"print(") && text[strlen(text)-1]==')') {
        if(!compile_expr(c,text))return 0;
        (*position)++;return 1;
    }
    if(starts(text,"let "))text=(char*)trim(text+4);
    else if(starts(text,"var "))text=(char*)trim(text+4);
    else if(starts(text,"keep "))text=(char*)trim(text+5);
    assign=find_assignment(text);
    if(assign>=0){
        char name[64];const char *expr;
        size_t n=(size_t)assign;
        while(n&&isspace((unsigned char)text[n-1]))n--;
        snprintf(name,sizeof(name),"%.*s",(int)n,text);
        expr=trim(text+assign+1);
        {
            int fast_assign = emit_fast_i64_add_assignment(c, name, expr);
            if (fast_assign < 0) return 0;
            if (fast_assign) {
                int slot = scope_find(c->scope, name, strlen(name));
                if (slot >= 0) c->scope->is_i64[slot] = 1;
            } else {
                int slot;
                if(!compile_expr(c,expr))return 0;
                slot=scope_slot(c->scope,name,strlen(name),1);
                if(slot<0||emit(c,MOP_STORE_LOCAL,slot,0,0)<0)return 0;
                c->scope->is_i64[slot] = (unsigned char)expr_is_i64_literal(expr);
                c->scope->i64_list_len[slot] = expr_i64_list_literal_len(expr);
            }
        }
        (*position)++;return 1;
    }
    if(!compile_expr(c,text))return 0;
    emit(c,MOP_POP,0,0,0);(*position)++;return 1;
}

static int compile_block(Compiler *c, int *position, int end, int indent) {
    while(*position<end){
        SourceLine *line=&c->lines[*position];
        char *text=(char*)trim(line->text);
        strip_inline_comment(text);
        text=(char*)trim(text);
        if(!*text||starts(text,"//")||*text=='#'){(*position)++;continue;}
        if(line->indent<indent)return 1;
        if(line->indent>indent){set_error(c,"unexpected indentation");return 0;}
        if(!compile_statement(c,position,end,indent))return 0;
    }
    return 1;
}

static int split_lines(Compiler *c, const char *source) {
    const char *p=source,*start=source;
    int number=1;
    while(1){
        if(*p=='\n'||!*p){
            size_t n=(size_t)(p-start),cap=c->line_count+1;
            int indent=0;
            SourceLine *grown=(SourceLine*)realloc(c->lines,sizeof(*grown)*(size_t)cap);
            char *line;
            if(!grown)return 0;
            c->lines=grown;
            if(n&&start[n-1]=='\r')n--;
            line=copy_text(start,n);if(!line)return 0;
            while(line[indent]==' ')indent++;
            c->lines[c->line_count++]=(SourceLine){line,indent,number++};
            if(!*p)break;
            start=++p;continue;
        }
        p++;
    }
    return 1;
}

static int line_module_is_builtin(const char *module) {
    return strcmp(module, "io") == 0 || strcmp(module, "sys") == 0 ||
           strcmp(module, "math") == 0 || strcmp(module, "time") == 0 ||
           strcmp(module, "gc") == 0 || strcmp(module, "thread") == 0 ||
           strcmp(module, "chan") == 0 || strcmp(module, "canvas") == 0 ||
           strcmp(module, "money") == 0 || strcmp(module, "server") == 0 ||
           strcmp(module, "ai") == 0 || strcmp(module, "std.ai") == 0 ||
           strcmp(module, "random") == 0 || strcmp(module, "std.random") == 0 ||
           strcmp(module, "string") == 0 || strcmp(module, "std.string") == 0 ||
           strcmp(module, "list") == 0 || strcmp(module, "std.list") == 0 ||
           strcmp(module, "map") == 0 || strcmp(module, "std.map") == 0 ||
           strcmp(module, "type") == 0 || strcmp(module, "std.type") == 0 ||
           strcmp(module, "json") == 0 || strcmp(module, "std.json") == 0 ||
           strcmp(module, "assert") == 0 || strcmp(module, "std.assert") == 0 ||
           strcmp(module, "event") == 0 || strcmp(module, "std.event") == 0 ||
           strcmp(module, "game") == 0 || strcmp(module, "std.game") == 0 ||
           strcmp(module, "data") == 0 || strcmp(module, "std.data") == 0;
}

static int parse_import_module_name(const char *line, char *module, size_t module_cap) {
    char tmp[512];
    char *rest = NULL;
    char *as_pos = NULL;
    size_t module_len;
    if (!line || !module || module_cap == 0) return 0;
    snprintf(tmp, sizeof(tmp), "%s", line);
    strip_inline_comment(tmp);
    rest = (char *)trim(tmp);
    if (starts(rest, "import ")) rest = (char *)trim(rest + 7);
    else if (starts(rest, "use ")) rest = (char *)trim(rest + 4);
    else if (starts(rest, "need ")) rest = (char *)trim(rest + 5);
    else return 0;
    as_pos = strstr(rest, " as ");
    if (!as_pos) return 0;
    module_len = (size_t)(as_pos - rest);
    while (module_len && isspace((unsigned char)rest[module_len - 1])) module_len--;
    if (module_len >= module_cap) module_len = module_cap - 1;
    memcpy(module, rest, module_len);
    module[module_len] = '\0';
    if (module[0] && (module[0] == '"' || module[0] == '\'') && module[strlen(module) - 1] == module[0]) {
        size_t n = strlen(module);
        memmove(module, module + 1, n - 2);
        module[n - 2] = '\0';
    }
    if (strncmp(module, "pkg:", 4) == 0) memmove(module, module + 4, strlen(module + 4) + 1);
    return *module != '\0';
}

