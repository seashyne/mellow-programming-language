/* Game runtime fragment 3: scenes, entities, AABB collision, and animation frames. */

static int std_game_scene_create_syscall(const MValue *args, size_t argc, MValue *out) {
    MValue scene, size;
    char *name = NULL;
    int64_t width = 320, height = 180;
    if (argc < 1 || argc > 3) return 0;
    if (argc > 1 && !std_game_integer(&args[1], &width)) return 0;
    if (argc > 2 && !std_game_integer(&args[2], &height)) return 0;
    name = std_text(&args[0], NULL);
    if (!name) return 0;
    if (!ai_map_new(&scene, 3)) { free(name); return 0; }
    ai_map_put(&scene, "name", mval_owned_copy(name, strlen(name)));
    free(name);
    if (!ai_list_new(&size, 2)) return 0;
    ai_list_push(&size, mval_i64(width));
    ai_list_push(&size, mval_i64(height));
    ai_map_put(&scene, "size", size);
    {
        MValue entities;
        if (!ai_list_new(&entities, 0)) return 0;
        ai_map_put(&scene, "entities", entities);
    }
    *out = scene;
    return 1;
}

static int std_game_entity_create_syscall(const MValue *args, size_t argc, MValue *out) {
    MValue entity, pos, size, vel, tags;
    char *id = NULL;
    double x = 0.0, y = 0.0, w = 1.0, h = 1.0;
    if (argc < 1 || argc > 6) return 0;
    if (argc > 1 && !std_game_number(&args[1], &x)) return 0;
    if (argc > 2 && !std_game_number(&args[2], &y)) return 0;
    if (argc > 3 && !std_game_number(&args[3], &w)) return 0;
    if (argc > 4 && !std_game_number(&args[4], &h)) return 0;
    id = std_text(&args[0], NULL);
    if (!id) return 0;
    if (!ai_map_new(&entity, 5)) { free(id); return 0; }
    ai_map_put(&entity, "id", mval_owned_copy(id, strlen(id)));
    free(id);
    pos = std_game_float_pair(x, y);
    ai_map_put(&entity, "pos", pos);
    size = std_game_float_pair(w, h);
    ai_map_put(&entity, "size", size);
    vel = std_game_float_pair(0.0, 0.0);
    ai_map_put(&entity, "vel", vel);
    if (argc > 5 && args[5].tag == MVAL_LIST)
        tags = std_clone(&args[5]);
    else if (!ai_list_new(&tags, 0))
        return 0;
    ai_map_put(&entity, "tags", tags);
    *out = entity;
    return 1;
}

static int std_game_entity_move_syscall(const MValue *args, size_t argc, MValue *out) {
    MValue entity;
    const MValue *pos;
    double px = 0.0, py = 0.0, dx = 0.0, dy = 0.0;
    if (argc < 1 || argc > 3) return 0;
    if (args[0].tag == MVAL_MAP)
        entity = std_clone(&args[0]);
    else {
        MValue fallback;
        if (!ai_map_new(&entity, 3)) return 0;
        fallback = std_game_float_pair(0.0, 0.0);
        std_map_set(&entity, ai_str("pos"), fallback);
    }
    if (argc > 1 && !std_game_number(&args[1], &dx)) { mvalue_free(&entity); return 0; }
    if (argc > 2 && !std_game_number(&args[2], &dy)) { mvalue_free(&entity); return 0; }
    pos = ai_map_get(&entity, "pos");
    if (pos && pos->tag == MVAL_LIST && pos->as.list.len >= 2) {
        if (!std_game_number(&pos->as.list.items[0], &px) ||
            !std_game_number(&pos->as.list.items[1], &py)) {
            mvalue_free(&entity);
            return 0;
        }
    }
    std_map_set(&entity, ai_str("pos"), std_game_float_pair(px + dx, py + dy));
    std_map_set(&entity, ai_str("vel"), std_game_float_pair(dx, dy));
    *out = entity;
    return 1;
}

static void std_game_box(const MValue *box, double *px, double *py,
                         double *sx, double *sy) {
    const MValue *pos, *size;
    *px = 0.0; *py = 0.0; *sx = 0.0; *sy = 0.0;
    if (!box || box->tag != MVAL_MAP) return;
    pos = ai_map_get(box, "pos");
    size = ai_map_get(box, "size");
    if (pos && pos->tag == MVAL_LIST && pos->as.list.len >= 2) {
        std_game_number(&pos->as.list.items[0], px);
        std_game_number(&pos->as.list.items[1], py);
    }
    if (size && size->tag == MVAL_LIST && size->as.list.len >= 2) {
        std_game_number(&size->as.list.items[0], sx);
        std_game_number(&size->as.list.items[1], sy);
    }
}

static int std_game_collide_syscall(const MValue *args, size_t argc, MValue *out) {
    double ax, ay, aw, ah, bx, by, bw, bh;
    int hit;
    if (argc != 2) return 0;
    std_game_box(&args[0], &ax, &ay, &aw, &ah);
    std_game_box(&args[1], &bx, &by, &bw, &bh);
    hit = !(ax + aw < bx || bx + bw < ax || ay + ah < by || by + bh < ay);
    *out = mval_bool(hit);
    return 1;
}

static int std_game_anim_syscall(const MValue *args, size_t argc, MValue *out) {
    int64_t frames = 1, index;
    double seconds = 0.0, fps = 12.0;
    int loop = 1;
    MValue result;
    if (argc < 1 || argc > 4) return 0;
    if (!std_game_integer(&args[0], &frames)) return 0;
    if (frames < 1) frames = 1;
    if (argc > 1 && !std_game_number(&args[1], &seconds)) return 0;
    if (argc > 2 && !std_game_number(&args[2], &fps)) return 0;
    if (argc > 3) loop = ai_truthy(&args[3]);
    index = (int64_t)(seconds * fps);
    if (loop) index = std_game_mod(index, frames);
    else if (index > frames - 1) index = frames - 1;
    if (!ai_map_new(&result, 2)) return 0;
    ai_map_put(&result, "frame", mval_i64(index));
    ai_map_put(&result, "frame_count", mval_i64(frames));
    *out = result;
    return 1;
}
