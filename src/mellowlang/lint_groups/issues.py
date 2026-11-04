"""What the linter reports and what it remembers: the issue record, the
builtin name table, and the scope chain that resolves declarations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Set


@dataclass
class LintIssue:
    kind: str
    message: str
    line: Optional[int] = None
    col: Optional[int] = None


_BUILTINS: Set[str] = {
    "print","show","input","ask","len","range","wait","stop","precision",
    "call","get","lib","true","false","none","null",
    "abs","min","max","floor","ceil","round","sqrt","pow","sin","cos","tan",
    "atan2","clamp","lerp","pi","log","sign","deg_to_rad","rad_to_deg",
    "distance","angle_between","fmod",
    "random","randi","rand","rand_int","rand_float","random_int","random_float",
    "global_seed","seed",
    "is_number","is_string","is_bool","is_list","is_map","is_none","type_of",
    "assert","assert_eq","assert_ne",
    "vec","vec2","vec3","vector",
    "vec_add","vec_sub","vec_mul","vec_dot","vec_len","vec_norm",
    "vec_dist","vec_lerp","vec_limit","vec_dim","vec_axis","vec_with",
    "list_push","list_pop","list_insert","list_remove","list_has","list_sort","list_len",
    "list_map","list_filter","list_find","list_slice","list_reverse","list_reduce","list_count",
    "map_get","map_set","map_keys","map_values","map_has",
    "str_len","str_lower","str_upper","str_trim","str_replace",
    "str_find","str_split","str_join","str_format",
    "string_len","string_lower","string_upper",
    "str_starts_with","str_ends_with","str_pad_left","str_pad_right","str_repeat","str_contains",
    "json_encode","json_decode",
    "enumerate","zip","sorted","reversed","any","all","sum",
    "str","int","float","bool","type",
    "money","money_of","money_add","money_sub","money_mul","money_div",
    "money_quantize","money_format","money_amount","money_currency",
    "money_eq","money_lt","money_gt",
    "data_open_jsonl","data_open_csv","data_next","data_close","data_cancel",
    "data_info","data_project","data_where","data_sum",
    "data_sqlite_open","data_sqlite_close","data_sqlite_query","data_sqlite_execute",
    "ledger_create","ledger_post","ledger_verify","ledger_balance","ledger_entries",
    "save_data","load_data","mkdir",
    "file_read","file_write","file_append","file_exists","file_delete",
    "save_init","save_set","save_get","save_commit","save_load",
    "save_list","save_delete","save_clear",
    "save_commit_signed","save_load_signed",
    "net_http_get","net_http_post",
    "net_ws_connect","net_ws_send","net_ws_recv","net_ws_close","net_ws_state",
    "astar","neighbors4","neighbors8","tween",
    "ease_linear","ease_in_quad","ease_out_quad","ease_in_out_quad",
    "ease_in_cubic","ease_out_cubic","ease_in_out_cubic",
    "ease_in_back","ease_out_back","ease_out_bounce","ease_out_elastic",
    "ai_seek","ai_flee","ai_arrive","ai_wander","ai_patrol",
    "ai_in_range","ai_in_sight","ai_nearest","ai_filter_range",
    "ai_decide","ai_utility","ai_bt","ai_fsm",
    "time_now","time_unix","time_ms",
    "emit",
}


@dataclass
class _VarInfo:
    line: Optional[int]
    used: bool = False
    param: bool = False
    loop_var: bool = False



class _Scope:
    def __init__(self, parent=None, fn_name=None):
        self.parent = parent
        self.fn_name = fn_name
        self.vars: Dict[str, _VarInfo] = {}

    def declare(self, name, line=None, param=False, loop_var=False):
        self.vars[name] = _VarInfo(line=line, param=param, loop_var=loop_var)

    def mark_used(self, name):
        if name in self.vars:
            self.vars[name].used = True
            return True
        if self.parent:
            return self.parent.mark_used(name)
        return False

    def is_declared(self, name):
        if name in self.vars: return True
        if self.parent: return self.parent.is_declared(name)
        return False

    def unused(self):
        return [
            (n, i) for n, i in self.vars.items()
            if not i.used and not i.param and not i.loop_var
            and not n.startswith("_")
        ]
