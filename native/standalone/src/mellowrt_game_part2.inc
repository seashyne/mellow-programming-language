/* Game runtime fragment 2: grid neighbors and A* pathfinding. */

static int std_game_neighbors_syscall(const MValue *args, size_t argc, MValue *out, int diagonal) {
    int64_t x, y, w, h;
    static const int moves[8][2] = {
        {1, 0}, {-1, 0}, {0, 1}, {0, -1},
        {1, 1}, {1, -1}, {-1, 1}, {-1, -1}
    };
    MValue list;
    size_t i, count = diagonal ? 8 : 4;
    if (argc != 4) return 0;
    if (!std_game_integer(&args[0], &x) || !std_game_integer(&args[1], &y) ||
        !std_game_integer(&args[2], &w) || !std_game_integer(&args[3], &h)) return 0;
    if (!ai_list_new(&list, count)) return 0;
    for (i = 0; i < count; ++i) {
        int64_t nx = x + moves[i][0], ny = y + moves[i][1];
        if (nx < 0 || nx >= w || ny < 0 || ny >= h) continue;
        std_list_append(&list, std_game_int_pair(nx, ny));
    }
    *out = list;
    return 1;
}

/* Read one grid cell; a missing row or cell counts as blocked, like Python's
 * exception path in the reference implementation. */
static int std_game_grid_cell(const MValue *grid, int64_t x, int64_t y, int64_t *out) {
    const MValue *row, *cell;
    if (!grid || grid->tag != MVAL_LIST || y < 0 || (size_t)y >= grid->as.list.len)
        return 0;
    row = &grid->as.list.items[y];
    if (row->tag != MVAL_LIST || x < 0 || (size_t)x >= row->as.list.len) return 0;
    cell = &row->as.list.items[x];
    return std_game_integer(cell, out);
}

static int std_game_blocked(const MValue *grid, int64_t x, int64_t y) {
    int64_t value;
    if (!std_game_grid_cell(grid, x, y, &value)) return 1;
    return value != 0;
}

typedef struct {
    double f;
    double g;
    int64_t x;
    int64_t y;
} StdGameNode;

typedef struct {
    StdGameNode *items;
    size_t len;
    size_t cap;
} StdGameHeap;

static int std_game_node_less(const StdGameNode *a, const StdGameNode *b) {
    if (a->f != b->f) return a->f < b->f;
    if (a->g != b->g) return a->g < b->g;
    if (a->x != b->x) return a->x < b->x;
    return a->y < b->y;
}

static int std_game_heap_push(StdGameHeap *heap, StdGameNode node) {
    size_t index;
    if (heap->len == heap->cap) {
        size_t next = heap->cap ? heap->cap * 2 : 32;
        StdGameNode *grown = (StdGameNode *)realloc(heap->items, next * sizeof(StdGameNode));
        if (!grown) return 0;
        heap->items = grown;
        heap->cap = next;
    }
    index = heap->len++;
    heap->items[index] = node;
    while (index > 0) {
        size_t parent = (index - 1) / 2;
        if (!std_game_node_less(&heap->items[index], &heap->items[parent])) break;
        {
            StdGameNode swap = heap->items[parent];
            heap->items[parent] = heap->items[index];
            heap->items[index] = swap;
        }
        index = parent;
    }
    return 1;
}

static int std_game_heap_pop(StdGameHeap *heap, StdGameNode *out) {
    size_t index = 0;
    if (heap->len == 0) return 0;
    *out = heap->items[0];
    heap->len--;
    if (heap->len == 0) return 1;
    heap->items[0] = heap->items[heap->len];
    while (1) {
        size_t left = index * 2 + 1, right = left + 1, best = index;
        if (left < heap->len && std_game_node_less(&heap->items[left], &heap->items[best]))
            best = left;
        if (right < heap->len && std_game_node_less(&heap->items[right], &heap->items[best]))
            best = right;
        if (best == index) break;
        {
            StdGameNode swap = heap->items[best];
            heap->items[best] = heap->items[index];
            heap->items[index] = swap;
        }
        index = best;
    }
    return 1;
}

static MValue std_game_reconstruct(long *came, long goal_index, int64_t width) {
    MValue path;
    long *stack = NULL;
    size_t depth = 0, cap = 0, i;
    long current = goal_index;
    if (!ai_list_new(&path, 8)) return mval_none();
    while (current >= 0) {
        if (depth == cap) {
            size_t next = cap ? cap * 2 : 16;
            long *grown = (long *)realloc(stack, next * sizeof(long));
            if (!grown) { free(stack); return path; }
            stack = grown;
            cap = next;
        }
        stack[depth++] = current;
        current = came[current];
    }
    for (i = depth; i > 0; --i) {
        long index = stack[i - 1];
        std_list_append(&path, std_game_int_pair(index % width, index / width));
    }
    free(stack);
    return path;
}

static int std_game_astar_syscall(MellowRuntimeContext *ctx, const MValue *args,
                                  size_t argc, MValue *out) {
    const MValue *grid, *start, *goal;
    int diagonal = 0;
    int64_t sx, sy, gx, gy, width, height, x, y;
    long *came = NULL;
    double *score = NULL;
    size_t cells, i;
    StdGameHeap heap;
    MValue path;
    static const int moves[8][2] = {
        {1, 0}, {-1, 0}, {0, 1}, {0, -1},
        {1, 1}, {1, -1}, {-1, 1}, {-1, -1}
    };
    size_t move_count = 4;
    int found = 0;

    if (argc < 3 || argc > 4) return 0;
    grid = &args[0];
    start = &args[1];
    goal = &args[2];
    if (argc >= 4) diagonal = ai_truthy(&args[3]);
    if (!grid || grid->tag != MVAL_LIST || grid->as.list.len == 0)
        return std_error(ctx, "std.game.path.astar: expected grid as non-empty list");
    if (grid->as.list.items[0].tag != MVAL_LIST)
        return std_error(ctx, "std.game.path.astar: expected grid as list of rows");
    if (!start || start->tag != MVAL_LIST || start->as.list.len != 2)
        return std_error(ctx, "std.game.path.astar: expected start [x,y]");
    if (!goal || goal->tag != MVAL_LIST || goal->as.list.len != 2)
        return std_error(ctx, "std.game.path.astar: expected goal [x,y]");
    height = (int64_t)grid->as.list.len;
    width = (int64_t)grid->as.list.items[0].as.list.len;
    if (width <= 0)
        return std_error(ctx, "std.game.path.astar: expected grid as list of rows");
    if (!std_game_integer(&start->as.list.items[0], &sx) ||
        !std_game_integer(&start->as.list.items[1], &sy) ||
        !std_game_integer(&goal->as.list.items[0], &gx) ||
        !std_game_integer(&goal->as.list.items[1], &gy)) return 0;

    *out = mval_none();
    if (sx < 0 || sx >= width || sy < 0 || sy >= height ||
        gx < 0 || gx >= width || gy < 0 || gy >= height) {
        if (!ai_list_new(out, 1)) return 0;
        return 1;
    }
    if (std_game_blocked(grid, sx, sy) || std_game_blocked(grid, gx, gy)) {
        if (!ai_list_new(out, 1)) return 0;
        return 1;
    }
    if ((uint64_t)width > (uint64_t)SIZE_MAX / (uint64_t)height) return 0;
    cells = (size_t)width * (size_t)height;
    came = (long *)malloc(cells * sizeof(long));
    score = (double *)malloc(cells * sizeof(double));
    if (!came || !score) { free(came); free(score); return 0; }
    for (i = 0; i < cells; ++i) { came[i] = -1; score[i] = 1.0e30; }

    memset(&heap, 0, sizeof(heap));
    if (diagonal) move_count = 8;
    score[(size_t)(sy * width + sx)] = 0.0;
    {
        StdGameNode first;
        int64_t dx = sx > gx ? sx - gx : gx - sx;
        int64_t dy = sy > gy ? sy - gy : gy - sy;
        first.g = 0.0;
        first.f = (double)(diagonal ? (dx > dy ? dx : dy) : dx + dy);
        first.x = sx;
        first.y = sy;
        if (!std_game_heap_push(&heap, first)) {
            free(came); free(score); free(heap.items);
            return 0;
        }
    }

    while (heap.len > 0) {
        StdGameNode node;
        size_t move_index;
        std_game_heap_pop(&heap, &node);
        x = node.x;
        y = node.y;
        if (x == gx && y == gy) { found = 1; break; }
        for (move_index = 0; move_index < move_count; ++move_index) {
            int64_t nx = x + moves[move_index][0];
            int64_t ny = y + moves[move_index][1];
            double step, next_score;
            long next_index;
            if (nx < 0 || nx >= width || ny < 0 || ny >= height) continue;
            if (std_game_blocked(grid, nx, ny)) continue;
            step = (moves[move_index][0] != 0 && moves[move_index][1] != 0)
                       ? 1.41421356237 : 1.0;
            next_score = node.g + step;
            next_index = ny * width + nx;
            if (next_score < score[next_index]) {
                StdGameNode pushed;
                int64_t dx = nx > gx ? nx - gx : gx - nx;
                int64_t dy = ny > gy ? ny - gy : gy - ny;
                came[next_index] = y * width + x;
                score[next_index] = next_score;
                pushed.g = next_score;
                pushed.f = next_score + (double)(diagonal ? (dx > dy ? dx : dy) : dx + dy);
                pushed.x = nx;
                pushed.y = ny;
                if (!std_game_heap_push(&heap, pushed)) break;
            }
        }
    }

    if (found)
        path = std_game_reconstruct(came, gy * width + gx, width);
    else if (!ai_list_new(&path, 1))
        path = mval_none();
    free(heap.items);
    free(came);
    free(score);
    *out = path;
    return 1;
}
