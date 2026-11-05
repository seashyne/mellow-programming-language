/* Game runtime fragment 4: AI steering and perception helpers. */

static int std_game_vec2(const MValue *value, double *x, double *y) {
    if (!value || value->tag != MVAL_LIST || value->as.list.len < 2) return 0;
    return std_game_number(&value->as.list.items[0], x) &&
           std_game_number(&value->as.list.items[1], y);
}

static MValue std_game_normalize(double vx, double vy, double speed) {
    double magnitude = sqrt(vx * vx + vy * vy);
    if (magnitude < 1e-9) return std_game_float_pair(0.0, 0.0);
    return std_game_float_pair(vx / magnitude * speed, vy / magnitude * speed);
}

static int std_game_seek_syscall(const MValue *args, size_t argc, MValue *out, int flee) {
    double px, py, tx, ty, speed;
    if (argc < 2 || argc > 3) return 0;
    if (!std_game_vec2(&args[0], &px, &py) || !std_game_vec2(&args[1], &tx, &ty))
        return 0;
    if (!std_game_opt_number(args, argc, 2, 1.0, &speed)) return 0;
    if (flee)
        *out = std_game_normalize(px - tx, py - ty, speed);
    else
        *out = std_game_normalize(tx - px, ty - py, speed);
    return 1;
}

static int std_game_arrive_syscall(const MValue *args, size_t argc, MValue *out) {
    double px, py, tx, ty, speed = 1.0, slow_radius = 50.0;
    double dx, dy, dist, effective;
    if (argc < 2 || argc > 4) return 0;
    if (!std_game_vec2(&args[0], &px, &py) || !std_game_vec2(&args[1], &tx, &ty))
        return 0;
    if (!std_game_opt_number(args, argc, 2, 1.0, &speed)) return 0;
    if (!std_game_opt_number(args, argc, 3, 50.0, &slow_radius)) return 0;
    dx = tx - px;
    dy = ty - py;
    dist = sqrt(dx * dx + dy * dy);
    if (dist < 1e-9) {
        *out = std_game_float_pair(0.0, 0.0);
        return 1;
    }
    effective = slow_radius > 0 ? speed * (dist / slow_radius < 1.0 ? dist / slow_radius : 1.0)
                                : speed;
    *out = std_game_float_pair(dx / dist * effective, dy / dist * effective);
    return 1;
}

static int std_game_wander_syscall(const MValue *args, size_t argc, MValue *out) {
    double angle = 0.0, speed = 1.0, jitter = 0.3, next_angle;
    MValue result, vel;
    if (argc < 1 || argc > 4) return 0;
    if (!std_game_opt_number(args, argc, 1, 0.0, &angle)) return 0;
    if (!std_game_opt_number(args, argc, 2, 1.0, &speed)) return 0;
    if (!std_game_opt_number(args, argc, 3, 0.3, &jitter)) return 0;
    next_angle = angle + jitter * sin(angle * 1.618);
    vel = std_game_float_pair(cos(next_angle) * speed, sin(next_angle) * speed);
    if (!ai_map_new(&result, 2)) { mvalue_free(&vel); return 0; }
    ai_map_put(&result, "vel", vel);
    ai_map_put(&result, "angle", mval_f64(next_angle));
    *out = result;
    return 1;
}

static int std_game_patrol_syscall(const MValue *args, size_t argc, MValue *out) {
    const MValue *waypoints, *waypoint;
    double px, py, dx, dy, dist, speed = 1.0, threshold = 5.0;
    int64_t index = 0, count;
    MValue result, vel;
    if (argc < 3 || argc > 5) return 0;
    if (!std_game_vec2(&args[0], &px, &py)) return 0;
    waypoints = &args[1];
    if (!std_game_opt_integer(args, argc, 2, 0, &index)) return 0;
    if (!std_game_opt_number(args, argc, 3, 1.0, &speed)) return 0;
    if (!std_game_opt_number(args, argc, 4, 5.0, &threshold)) return 0;
    if (waypoints->tag != MVAL_LIST || waypoints->as.list.len == 0) {
        if (!ai_map_new(&result, 2)) return 0;
        ai_map_put(&result, "vel", std_game_float_pair(0.0, 0.0));
        ai_map_put(&result, "idx", mval_i64(0));
        *out = result;
        return 1;
    }
    count = (int64_t)waypoints->as.list.len;
    index = std_game_mod(index, count);
    waypoint = &waypoints->as.list.items[index];
    if (!std_game_vec2(waypoint, &dx, &dy)) return 0;
    dx -= px;
    dy -= py;
    dist = sqrt(dx * dx + dy * dy);
    if (dist < threshold) {
        index = std_game_mod(index + 1, count);
        waypoint = &waypoints->as.list.items[index];
        if (!std_game_vec2(waypoint, &dx, &dy)) return 0;
        dx -= px;
        dy -= py;
        dist = sqrt(dx * dx + dy * dy);
    }
    vel = dist > 1e-9 ? std_game_normalize(dx, dy, speed) : std_game_float_pair(0.0, 0.0);
    if (!ai_map_new(&result, 2)) { mvalue_free(&vel); return 0; }
    ai_map_put(&result, "vel", vel);
    ai_map_put(&result, "idx", mval_i64(index));
    *out = result;
    return 1;
}

static int std_game_in_range_syscall(const MValue *args, size_t argc, MValue *out) {
    double px, py, tx, ty, radius, dx, dy;
    if (argc != 3) return 0;
    if (!std_game_vec2(&args[0], &px, &py) || !std_game_vec2(&args[1], &tx, &ty))
        return 0;
    if (!std_game_number(&args[2], &radius)) return 0;
    dx = tx - px;
    dy = ty - py;
    *out = mval_bool(dx * dx + dy * dy <= radius * radius);
    return 1;
}

static int std_game_in_sight_syscall(const MValue *args, size_t argc, MValue *out) {
    double px, py, facing, tx, ty, fov = 90.0, max_dist = 200.0;
    double dx, dy, dist, angle, diff;
    if (argc < 3 || argc > 5) return 0;
    if (!std_game_vec2(&args[0], &px, &py)) return 0;
    if (!std_game_number(&args[1], &facing)) return 0;
    if (!std_game_vec2(&args[2], &tx, &ty)) return 0;
    if (!std_game_opt_number(args, argc, 3, 90.0, &fov)) return 0;
    if (!std_game_opt_number(args, argc, 4, 200.0, &max_dist)) return 0;
    dx = tx - px;
    dy = ty - py;
    dist = sqrt(dx * dx + dy * dy);
    if (dist > max_dist || dist < 1e-9) { *out = mval_bool(0); return 1; }
    angle = atan2(dy, dx) * (180.0 / 3.14159265358979323846);
    diff = std_game_mod_double(angle - facing + 180.0, 360.0) - 180.0;
    *out = mval_bool(fabs(diff) <= fov / 2.0);
    return 1;
}

/* Position of a target: [x, y, ...] itself, or its "pos" entry. */
static const MValue *std_game_target_pos(const MValue *target) {
    const MValue *pos;
    if (!target) return NULL;
    if (target->tag == MVAL_LIST) {
        if (target->as.list.len >= 2) return target;
        return NULL;
    }
    if (target->tag != MVAL_MAP) return NULL;
    pos = ai_map_get(target, "pos");
    if (!pos || pos->tag != MVAL_LIST || pos->as.list.len < 2) return NULL;
    return pos;
}

static int std_game_nearest_syscall(const MValue *args, size_t argc, MValue *out) {
    const MValue *targets;
    double px, py, best = 1.0e30;
    const MValue *winner = NULL;
    size_t i;
    if (argc != 2) return 0;
    if (!std_game_vec2(&args[0], &px, &py)) return 0;
    targets = &args[1];
    if (targets->tag != MVAL_LIST || targets->as.list.len == 0) {
        *out = mval_none();
        return 1;
    }
    for (i = 0; i < targets->as.list.len; ++i) {
        const MValue *item = &targets->as.list.items[i];
        const MValue *pos = std_game_target_pos(item);
        double tx, ty, dx, dy, distance;
        if (!pos || !std_game_vec2(pos, &tx, &ty)) continue;
        dx = tx - px;
        dy = ty - py;
        distance = dx * dx + dy * dy;
        if (distance < best) { best = distance; winner = item; }
    }
    *out = winner ? std_clone(winner) : mval_none();
    return 1;
}

static int std_game_filter_range_syscall(const MValue *args, size_t argc, MValue *out) {
    const MValue *targets;
    double px, py, radius, limit;
    MValue result;
    size_t i;
    if (argc != 3) return 0;
    if (!std_game_vec2(&args[0], &px, &py)) return 0;
    targets = &args[1];
    if (!std_game_number(&args[2], &radius)) return 0;
    limit = radius * radius;
    if (!ai_list_new(&result, targets->tag == MVAL_LIST ? targets->as.list.len : 0))
        return 0;
    if (targets->tag != MVAL_LIST) { *out = result; return 1; }
    for (i = 0; i < targets->as.list.len; ++i) {
        const MValue *item = &targets->as.list.items[i];
        const MValue *pos = std_game_target_pos(item);
        double tx, ty, dx, dy;
        if (!pos || !std_game_vec2(pos, &tx, &ty)) continue;
        dx = tx - px;
        dy = ty - py;
        if (dx * dx + dy * dy <= limit) std_list_append(&result, std_clone(item));
    }
    *out = result;
    return 1;
}
