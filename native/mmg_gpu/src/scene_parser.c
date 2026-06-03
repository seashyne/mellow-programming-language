#include "mmg_gpu.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void trim_newline(char* s) {
    size_t n = strlen(s);
    while (n > 0 && (s[n - 1] == '\n' || s[n - 1] == '\r')) s[--n] = '\0';
}

static MMGActionType parse_action(const char* text) {
    if (strcmp(text, "CLOSE") == 0) return MMG_ACTION_CLOSE;
    if (strcmp(text, "PRINT") == 0) return MMG_ACTION_PRINT;
    if (strcmp(text, "SET") == 0) return MMG_ACTION_SET;
    if (strcmp(text, "INC") == 0) return MMG_ACTION_INC;
    if (strcmp(text, "TOGGLE") == 0) return MMG_ACTION_TOGGLE;
    return MMG_ACTION_NOOP;
}

static MMGEventType parse_event(const char* text) {
    if (strcmp(text, "mouse") == 0 || strcmp(text, "MOUSE") == 0) return MMG_EVENT_MOUSE;
    return MMG_EVENT_KEY;
}

static MMGStateType parse_state_type(const char* text) {
    if (strcmp(text, "int") == 0) return MMG_STATE_INT;
    if (strcmp(text, "float") == 0) return MMG_STATE_FLOAT;
    if (strcmp(text, "bool") == 0) return MMG_STATE_BOOL;
    return MMG_STATE_STR;
}

int mmg_parse_scene(const char* path, MMGScene* out_scene) {
    memset(out_scene, 0, sizeof(*out_scene));
    strcpy(out_scene->app.title, "MMG GPU App");
    out_scene->app.width = 960;
    out_scene->app.height = 640;
    out_scene->app.clear[0] = 0.05f; out_scene->app.clear[1] = 0.07f; out_scene->app.clear[2] = 0.09f; out_scene->app.clear[3] = 1.0f;
    out_scene->app.zoom = 1.0f;
    out_scene->app.fps = 60;
    out_scene->app.escape_closes = 1;

    FILE* f = fopen(path, "rb");
    if (!f) return 1;
    char line[2048];
    while (fgets(line, sizeof(line), f)) {
        trim_newline(line);
        char* s = line;
        while (*s == ' ' || *s == '\t') ++s;
        if (!*s || *s == '#') continue;
        if (strncmp(s, "MMGSCENE", 8) == 0) continue;
        if (strncmp(s, "APP", 3) == 0) {
            sscanf(s, "APP \"%255[^\"]\" %d %d", out_scene->app.title, &out_scene->app.width, &out_scene->app.height);
        } else if (strncmp(s, "CLEAR", 5) == 0) {
            sscanf(s + 5, "%f %f %f %f", &out_scene->app.clear[0], &out_scene->app.clear[1], &out_scene->app.clear[2], &out_scene->app.clear[3]);
        } else if (strncmp(s, "CAMERA", 6) == 0) {
            sscanf(s + 6, "%f %f %f", &out_scene->app.camera_x, &out_scene->app.camera_y, &out_scene->app.zoom);
        } else if (strncmp(s, "FRAME", 5) == 0) {
            sscanf(s + 5, "%d", &out_scene->app.fps);
        } else if (strncmp(s, "PIPELINE", 8) == 0) {
            if (strstr(s, "sprite_batching=1")) out_scene->app.enable_sprite_batching = 1;
            if (strstr(s, "shader_pipeline=1")) out_scene->app.enable_shader_pipeline = 1;
            if (strstr(s, "input_callbacks=1")) out_scene->app.enable_input_callbacks = 1;
            if (strstr(s, "state_callbacks=1")) out_scene->app.enable_state_callbacks = 1;
            if (strstr(s, "runtime_bridge=1")) out_scene->app.enable_runtime_bridge = 1;
        } else if (strncmp(s, "SHADER", 6) == 0) {
            if (out_scene->shader_count >= MMG_MAX_SHADERS) continue;
            MMGShaderRef* sh = &out_scene->shaders[out_scene->shader_count++];
            sscanf(s, "SHADER \"%63[^\"]\" \"%511[^\"]\" \"%511[^\"]\"", sh->name, sh->vert_path, sh->frag_path);
        } else if (strncmp(s, "TEXTURE", 7) == 0) {
            if (out_scene->texture_count >= MMG_MAX_TEXTURES) continue;
            MMGTexture* t = &out_scene->textures[out_scene->texture_count++];
            sscanf(s, "TEXTURE \"%127[^\"]\" \"%511[^\"]\"", t->id, t->source);
        } else if (strncmp(s, "SCENE", 5) == 0) {
            if (out_scene->scene_count >= MMG_MAX_SCENES) continue;
            MMGSceneRef* ref = &out_scene->scenes[out_scene->scene_count++];
            sscanf(s, "SCENE \"%127[^\"]\" %d", ref->id, &ref->active);
        } else if (strncmp(s, "SPRITE", 6) == 0) {
            if (out_scene->sprite_count >= MMG_MAX_SPRITES) continue;
            MMGSprite* sp = &out_scene->sprites[out_scene->sprite_count++];
            sscanf(s, "SPRITE \"%127[^\"]\" \"%127[^\"]\" %f %f %f %f %f %f %f %f", sp->id, sp->texture, &sp->x, &sp->y, &sp->w, &sp->h, &sp->color[0], &sp->color[1], &sp->color[2], &sp->color[3]);
        } else if (strncmp(s, "BATCH_GROUP", 11) == 0) {
            if (out_scene->batch_count >= MMG_MAX_BATCHES) continue;
            MMGBatchGroup* bg = &out_scene->batches[out_scene->batch_count++];
            sscanf(s, "BATCH_GROUP \"%127[^\"]\" \"%127[^\"]\" %d", bg->scene_id, bg->texture, &bg->count);
        } else if (strncmp(s, "RECT", 4) == 0) {
            if (out_scene->rect_count >= MMG_MAX_RECTS) continue;
            MMGRect* r = &out_scene->rects[out_scene->rect_count++];
            sscanf(s + 4, "%f %f %f %f %f %f %f %f", &r->x, &r->y, &r->w, &r->h, &r->color[0], &r->color[1], &r->color[2], &r->color[3]);
        } else if (strncmp(s, "CIRCLE", 6) == 0) {
            if (out_scene->circle_count >= MMG_MAX_CIRCLES) continue;
            MMGCircle* c = &out_scene->circles[out_scene->circle_count++];
            sscanf(s + 6, "%f %f %f %f %f %f %f", &c->x, &c->y, &c->r, &c->color[0], &c->color[1], &c->color[2], &c->color[3]);
        } else if (strncmp(s, "LINE", 4) == 0) {
            if (out_scene->line_count >= MMG_MAX_LINES) continue;
            MMGLine* l = &out_scene->lines[out_scene->line_count++];
            sscanf(s + 4, "%f %f %f %f %f %f %f %f %f", &l->x1, &l->y1, &l->x2, &l->y2, &l->color[0], &l->color[1], &l->color[2], &l->color[3], &l->width);
        } else if (strncmp(s, "TEXT", 4) == 0) {
            if (out_scene->text_count >= MMG_MAX_TEXTS) continue;
            MMGText* t = &out_scene->texts[out_scene->text_count++];
            sscanf(s, "TEXT %f %f %d %f %f %f %f", &t->x, &t->y, &t->size, &t->color[0], &t->color[1], &t->color[2], &t->color[3]);
            const char* start = strchr(s, '"');
            const char* end = strrchr(s, '"');
            if (start && end && end > start) {
                size_t len = (size_t)(end - start - 1);
                if (len >= sizeof(t->text)) len = sizeof(t->text) - 1;
                memcpy(t->text, start + 1, len); t->text[len] = '\0';
            }
        } else if (strncmp(s, "STATE", 5) == 0 || strncmp(s, "BRIDGE_STATE", 12) == 0) {
            if (out_scene->state_count >= MMG_MAX_STATE) continue;
            MMGStateEntry* st = &out_scene->state[out_scene->state_count++];
            char typebuf[32] = {0};
            sscanf(s + (strncmp(s, "STATE", 5) == 0 ? 5 : 12), " \"%127[^\"]\" %31s \"%255[^\"]\"", st->key, typebuf, st->value);
            st->type = parse_state_type(typebuf);
        } else if (strncmp(s, "ON_KEY", 6) == 0 || strncmp(s, "ON_MOUSE", 8) == 0) {
            if (out_scene->event_count >= MMG_MAX_EVENTS) continue;
            MMGEventBinding* ev = &out_scene->events[out_scene->event_count++];
            char action[32] = {0};
            sscanf(s + (s[3] == 'K' ? 6 : 8), " \"%63[^\"]\" %31s \"%255[^\"]\"", ev->match, action, ev->payload);
            ev->type = (s[3] == 'K') ? MMG_EVENT_KEY : MMG_EVENT_MOUSE;
            ev->action = parse_action(action);
        } else if (strncmp(s, "BRIDGE_EVENT", 12) == 0) {
            if (out_scene->bridge_callback_count >= MMG_MAX_BRIDGE_CALLBACKS) continue;
            MMGBridgeCallback* cb = &out_scene->bridge_callbacks[out_scene->bridge_callback_count++];
            char event_name[16] = {0};
            char action[32] = {0};
            sscanf(s, "BRIDGE_EVENT \"%15[^\"]\" \"%63[^\"]\" %31s \"%255[^\"]\"", event_name, cb->match, action, cb->payload);
            cb->type = parse_event(event_name);
            cb->action = parse_action(action);
        }
    }
    fclose(f);
    return 0;
}
