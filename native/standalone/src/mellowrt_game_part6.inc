/* Game runtime fragment 6: syscall dispatch for std.game and the AI helpers. */

static int std_game_syscall(MellowRuntimeContext *ctx, int id, const MValue *args,
                            size_t argc, MValue *out) {
    switch (id) {
    case 156: return std_game_seek_syscall(args, argc, out, 0);
    case 157: return std_game_seek_syscall(args, argc, out, 1);
    case 158: return std_game_arrive_syscall(args, argc, out);
    case 159: return std_game_wander_syscall(args, argc, out);
    case 160: return std_game_patrol_syscall(args, argc, out);
    case 161: return std_game_in_range_syscall(args, argc, out);
    case 162: return std_game_in_sight_syscall(args, argc, out);
    case 163: return std_game_nearest_syscall(args, argc, out);
    case 164: return std_game_filter_range_syscall(args, argc, out);
    case 165: return std_game_utility_syscall(ctx, args, argc, out);
    case 166: return std_game_bt_syscall(ctx, args, argc, out);
    case 167: return std_game_fsm_syscall(ctx, args, argc, out);
    case 351: return std_game_tween_syscall(args, argc, out);
    case 352: return std_game_neighbors_syscall(args, argc, out, 0);
    case 353: return std_game_neighbors_syscall(args, argc, out, 1);
    case 354: return std_game_astar_syscall(ctx, args, argc, out);
    case 355: return std_game_scene_create_syscall(args, argc, out);
    case 356: return std_game_entity_create_syscall(args, argc, out);
    case 357: return std_game_entity_move_syscall(args, argc, out);
    case 358: return std_game_collide_syscall(args, argc, out);
    case 359: return std_game_anim_syscall(args, argc, out);
    default:
        if (id >= 340 && id <= 350)
            return std_game_ease_syscall(args, argc, out, id);
        return 0;
    }
}
