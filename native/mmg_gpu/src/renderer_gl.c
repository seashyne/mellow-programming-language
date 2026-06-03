#include "mmg_gpu.h"

#include <SDL2/SDL.h>
#include <SDL2/SDL_opengl.h>
#ifdef MMG_HAS_SDL2_IMAGE
#include <SDL2/SDL_image.h>
#endif
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    GLuint sprite_program;
    GLuint color_program;
    GLuint sprite_vbo;
    int ready;
} MMGPipeline;

static char* slurp_text(const char* path) {
    FILE* f = fopen(path, "rb");
    if (!f) return NULL;
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    char* buf = (char*)malloc((size_t)n + 1);
    if (!buf) { fclose(f); return NULL; }
    fread(buf, 1, (size_t)n, f);
    fclose(f);
    buf[n] = '\0';
    return buf;
}

static GLuint compile_shader(GLenum type, const char* path) {
    char* src = slurp_text(path);
    if (!src) return 0;
    GLuint sh = glCreateShader(type);
    glShaderSource(sh, 1, (const GLchar* const*)&src, NULL);
    glCompileShader(sh);
    free(src);
    GLint ok = 0;
    glGetShaderiv(sh, GL_COMPILE_STATUS, &ok);
    if (!ok) {
        char log[1024]; GLsizei len = 0; glGetShaderInfoLog(sh, sizeof(log), &len, log);
        fprintf(stderr, "shader compile failed for %s: %.*s\n", path, (int)len, log);
        glDeleteShader(sh);
        return 0;
    }
    return sh;
}

static GLuint link_program(const char* vert_path, const char* frag_path) {
    GLuint vs = compile_shader(GL_VERTEX_SHADER, vert_path);
    GLuint fs = compile_shader(GL_FRAGMENT_SHADER, frag_path);
    if (!vs || !fs) return 0;
    GLuint prog = glCreateProgram();
    glAttachShader(prog, vs); glAttachShader(prog, fs);
    glBindAttribLocation(prog, 0, "a_pos");
    glBindAttribLocation(prog, 1, "a_uv");
    glBindAttribLocation(prog, 2, "a_color");
    glLinkProgram(prog);
    glDeleteShader(vs); glDeleteShader(fs);
    GLint ok = 0;
    glGetProgramiv(prog, GL_LINK_STATUS, &ok);
    if (!ok) {
        char log[1024]; GLsizei len = 0; glGetProgramInfoLog(prog, sizeof(log), &len, log);
        fprintf(stderr, "program link failed: %.*s\n", (int)len, log);
        glDeleteProgram(prog);
        return 0;
    }
    return prog;
}

static void setup_ortho(int width, int height, float cam_x, float cam_y, float zoom) {
    glViewport(0, 0, width, height);
    glMatrixMode(GL_PROJECTION);
    glLoadIdentity();
    glOrtho(cam_x, cam_x + (double)width / zoom, cam_y + (double)height / zoom, cam_y, -1.0, 1.0);
    glMatrixMode(GL_MODELVIEW);
    glLoadIdentity();
}

static void draw_rect(float x, float y, float w, float h, const float c[4]) {
    glColor4f(c[0], c[1], c[2], c[3]);
    glBegin(GL_QUADS);
    glVertex2f(x, y); glVertex2f(x + w, y); glVertex2f(x + w, y + h); glVertex2f(x, y + h);
    glEnd();
}

static void draw_line(const MMGLine* l) {
    glColor4f(l->color[0], l->color[1], l->color[2], l->color[3]);
    glLineWidth(l->width > 0.0f ? l->width : 1.0f);
    glBegin(GL_LINES); glVertex2f(l->x1, l->y1); glVertex2f(l->x2, l->y2); glEnd();
}

static void draw_circle(const MMGCircle* c) {
    glColor4f(c->color[0], c->color[1], c->color[2], c->color[3]);
    glBegin(GL_TRIANGLE_FAN);
    glVertex2f(c->x, c->y);
    for (int i = 0; i <= 32; ++i) {
        float a = (float)i / 32.0f * 6.28318530718f;
        glVertex2f(c->x + cosf(a) * c->r, c->y + sinf(a) * c->r);
    }
    glEnd();
}

static MMGTexture* find_texture(MMGScene* scene, const char* id) {
    for (size_t i = 0; i < scene->texture_count; ++i) if (strcmp(scene->textures[i].id, id) == 0) return &scene->textures[i];
    return NULL;
}

static void ensure_texture(MMGTexture* tex) {
    if (!tex || tex->loaded) return;
    SDL_Surface* surf = NULL;
#ifdef MMG_HAS_SDL2_IMAGE
    if (tex->source[0]) surf = IMG_Load(tex->source);
#endif
    if (!surf && tex->source[0]) surf = SDL_LoadBMP(tex->source);
    if (!surf) {
        Uint32 pixels[4] = {0xffffffffu, 0xff4444ffu, 0xff4444ffu, 0xffffffffu};
        surf = SDL_CreateRGBSurfaceFrom(pixels, 2, 2, 32, 2 * 4, 0x000000ff, 0x0000ff00, 0x00ff0000, 0xff000000);
    }
    GLenum fmt = surf->format->BytesPerPixel == 4 ? GL_RGBA : GL_RGB;
    glGenTextures(1, &tex->gl_id);
    glBindTexture(GL_TEXTURE_2D, tex->gl_id);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
    glTexImage2D(GL_TEXTURE_2D, 0, fmt, surf->w, surf->h, 0, fmt, GL_UNSIGNED_BYTE, surf->pixels);
    tex->width = surf->w; tex->height = surf->h; tex->loaded = 1;
    SDL_FreeSurface(surf);
}

void mmg_dispatch_runtime_bridge(MMGScene* scene, const MMGBridgeCallback* cb) {
    if (!scene || !cb) return;
    fprintf(stdout, "[mmg-bridge] action=%d match=%s payload=%s\n", (int)cb->action, cb->match, cb->payload);
    if (cb->action == MMG_ACTION_SET || cb->action == MMG_ACTION_INC || cb->action == MMG_ACTION_TOGGLE) {
        for (size_t i = 0; i < scene->state_count; ++i) {
            if (strcmp(scene->state[i].key, cb->payload) == 0) {
                if (cb->action == MMG_ACTION_INC && scene->state[i].type == MMG_STATE_INT) {
                    int value = atoi(scene->state[i].value); snprintf(scene->state[i].value, sizeof(scene->state[i].value), "%d", value + 1);
                } else if (cb->action == MMG_ACTION_TOGGLE && scene->state[i].type == MMG_STATE_BOOL) {
                    snprintf(scene->state[i].value, sizeof(scene->state[i].value), "%d", strcmp(scene->state[i].value, "1") == 0 ? 0 : 1);
                }
                break;
            }
        }
    }
}

static void init_pipeline(MMGPipeline* pipe, const MMGScene* scene) {
    memset(pipe, 0, sizeof(*pipe));
    if (!scene->app.enable_shader_pipeline || scene->shader_count == 0) return;
    const char* sprite_vert = NULL; const char* sprite_frag = NULL;
    const char* color_vert = NULL; const char* color_frag = NULL;
    for (size_t i = 0; i < scene->shader_count; ++i) {
        if (strcmp(scene->shaders[i].name, "sprite") == 0) { sprite_vert = scene->shaders[i].vert_path; sprite_frag = scene->shaders[i].frag_path; }
        if (strcmp(scene->shaders[i].name, "color") == 0) { color_vert = scene->shaders[i].vert_path; color_frag = scene->shaders[i].frag_path; }
    }
    if (sprite_vert && sprite_frag) pipe->sprite_program = link_program(sprite_vert, sprite_frag);
    if (color_vert && color_frag) pipe->color_program = link_program(color_vert, color_frag);
    glGenBuffers(1, &pipe->sprite_vbo);
    pipe->ready = (pipe->sprite_vbo != 0);
}

static void upload_sprite_batch(GLuint vbo, const MMGSpriteVertex* vertices, size_t count) {
    glBindBuffer(GL_ARRAY_BUFFER, vbo);
    glBufferData(GL_ARRAY_BUFFER, (GLsizeiptr)(count * sizeof(MMGSpriteVertex)), vertices, GL_DYNAMIC_DRAW);
}

static void draw_sprite_batches(MMGScene* scene, MMGPipeline* pipe) {
    if (!scene->app.enable_sprite_batching || !pipe->ready || !pipe->sprite_program) {
        for (size_t i = 0; i < scene->sprite_count; ++i) {
            MMGTexture* tex = find_texture(scene, scene->sprites[i].texture);
            if (tex) ensure_texture(tex);
            if (tex && tex->loaded) {
                glEnable(GL_TEXTURE_2D); glBindTexture(GL_TEXTURE_2D, tex->gl_id);
                glColor4f(scene->sprites[i].color[0], scene->sprites[i].color[1], scene->sprites[i].color[2], scene->sprites[i].color[3]);
                glBegin(GL_QUADS);
                glTexCoord2f(0.f, 0.f); glVertex2f(scene->sprites[i].x, scene->sprites[i].y);
                glTexCoord2f(1.f, 0.f); glVertex2f(scene->sprites[i].x + scene->sprites[i].w, scene->sprites[i].y);
                glTexCoord2f(1.f, 1.f); glVertex2f(scene->sprites[i].x + scene->sprites[i].w, scene->sprites[i].y + scene->sprites[i].h);
                glTexCoord2f(0.f, 1.f); glVertex2f(scene->sprites[i].x, scene->sprites[i].y + scene->sprites[i].h);
                glEnd(); glDisable(GL_TEXTURE_2D);
            } else {
                draw_rect(scene->sprites[i].x, scene->sprites[i].y, scene->sprites[i].w, scene->sprites[i].h, scene->sprites[i].color);
            }
        }
        return;
    }

    glUseProgram(pipe->sprite_program);
    GLint u_view_size = glGetUniformLocation(pipe->sprite_program, "u_view_size");
    GLint u_tex = glGetUniformLocation(pipe->sprite_program, "u_tex");
    glUniform2f(u_view_size, (float)scene->app.width, (float)scene->app.height);
    glUniform1i(u_tex, 0);
    glEnable(GL_TEXTURE_2D);
    glEnableClientState(GL_VERTEX_ARRAY);
    glEnableClientState(GL_TEXTURE_COORD_ARRAY);
    glEnableClientState(GL_COLOR_ARRAY);

    MMGSpriteVertex* vertices = (MMGSpriteVertex*)malloc(scene->sprite_count * 6 * sizeof(MMGSpriteVertex));
    size_t vertex_count = 0;
    char current_texture[128] = {0};
    GLuint current_gl_id = 0;
    for (size_t i = 0; i < scene->sprite_count; ++i) {
        MMGSprite* s = &scene->sprites[i];
        MMGTexture* tex = find_texture(scene, s->texture);
        if (tex) ensure_texture(tex);
        if (!tex || !tex->loaded) continue;
        if (current_gl_id == 0) { strcpy(current_texture, s->texture); current_gl_id = tex->gl_id; }
        if (strcmp(current_texture, s->texture) != 0) {
            upload_sprite_batch(pipe->sprite_vbo, vertices, vertex_count);
            glBindTexture(GL_TEXTURE_2D, current_gl_id);
            glBindBuffer(GL_ARRAY_BUFFER, pipe->sprite_vbo);
            glVertexPointer(2, GL_FLOAT, sizeof(MMGSpriteVertex), (void*)0);
            glTexCoordPointer(2, GL_FLOAT, sizeof(MMGSpriteVertex), (void*)(sizeof(float) * 2));
            glColorPointer(4, GL_FLOAT, sizeof(MMGSpriteVertex), (void*)(sizeof(float) * 4));
            glDrawArrays(GL_TRIANGLES, 0, (GLsizei)vertex_count);
            vertex_count = 0; strcpy(current_texture, s->texture); current_gl_id = tex->gl_id;
        }
        MMGSpriteVertex quad[6] = {
            {s->x, s->y, 0.f, 0.f, s->color[0], s->color[1], s->color[2], s->color[3]},
            {s->x + s->w, s->y, 1.f, 0.f, s->color[0], s->color[1], s->color[2], s->color[3]},
            {s->x + s->w, s->y + s->h, 1.f, 1.f, s->color[0], s->color[1], s->color[2], s->color[3]},
            {s->x, s->y, 0.f, 0.f, s->color[0], s->color[1], s->color[2], s->color[3]},
            {s->x + s->w, s->y + s->h, 1.f, 1.f, s->color[0], s->color[1], s->color[2], s->color[3]},
            {s->x, s->y + s->h, 0.f, 1.f, s->color[0], s->color[1], s->color[2], s->color[3]},
        };
        memcpy(&vertices[vertex_count], quad, sizeof(quad));
        vertex_count += 6;
    }
    if (vertex_count > 0 && current_gl_id) {
        upload_sprite_batch(pipe->sprite_vbo, vertices, vertex_count);
        glBindTexture(GL_TEXTURE_2D, current_gl_id);
        glBindBuffer(GL_ARRAY_BUFFER, pipe->sprite_vbo);
        glVertexPointer(2, GL_FLOAT, sizeof(MMGSpriteVertex), (void*)0);
        glTexCoordPointer(2, GL_FLOAT, sizeof(MMGSpriteVertex), (void*)(sizeof(float) * 2));
        glColorPointer(4, GL_FLOAT, sizeof(MMGSpriteVertex), (void*)(sizeof(float) * 4));
        glDrawArrays(GL_TRIANGLES, 0, (GLsizei)vertex_count);
    }
    free(vertices);
    glDisableClientState(GL_COLOR_ARRAY);
    glDisableClientState(GL_TEXTURE_COORD_ARRAY);
    glDisableClientState(GL_VERTEX_ARRAY);
    glDisable(GL_TEXTURE_2D);
    glUseProgram(0);
}

int mmg_run_scene(const MMGScene* input_scene) {
    MMGScene scene = *input_scene;
    if (SDL_Init(SDL_INIT_VIDEO) != 0) { fprintf(stderr, "SDL_Init failed: %s\n", SDL_GetError()); return 2; }
#ifdef MMG_HAS_SDL2_IMAGE
    IMG_Init(IMG_INIT_PNG | IMG_INIT_JPG);
#endif
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, 2);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, 1);
    SDL_GL_SetAttribute(SDL_GL_DOUBLEBUFFER, 1);
    SDL_Window* window = SDL_CreateWindow(scene.app.title, SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED, scene.app.width, scene.app.height, SDL_WINDOW_OPENGL | SDL_WINDOW_SHOWN);
    if (!window) { fprintf(stderr, "SDL_CreateWindow failed: %s\n", SDL_GetError()); SDL_Quit(); return 3; }
    SDL_GLContext ctx = SDL_GL_CreateContext(window);
    if (!ctx) { fprintf(stderr, "SDL_GL_CreateContext failed: %s\n", SDL_GetError()); SDL_DestroyWindow(window); SDL_Quit(); return 4; }
    SDL_GL_SetSwapInterval(1);
    glDisable(GL_DEPTH_TEST);
    glEnable(GL_BLEND);
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
    MMGPipeline pipe; init_pipeline(&pipe, &scene);
    int running = 1;
    Uint32 frame_ms = scene.app.fps > 0 ? (1000u / (Uint32)scene.app.fps) : 16u;
    while (running) {
        Uint32 start = SDL_GetTicks();
        SDL_Event e;
        while (SDL_PollEvent(&e)) {
            if (e.type == SDL_QUIT) running = 0;
            if (e.type == SDL_KEYDOWN) {
                if (e.key.keysym.sym == SDLK_ESCAPE && scene.app.escape_closes) running = 0;
                for (size_t i = 0; i < scene.event_count; ++i) {
                    MMGEventBinding* ev = &scene.events[i];
                    int match = (strcmp(ev->match, "Escape") == 0 && e.key.keysym.sym == SDLK_ESCAPE) || (strcmp(ev->match, "Space") == 0 && e.key.keysym.sym == SDLK_SPACE);
                    if (ev->type == MMG_EVENT_KEY && match) {
                        if (ev->action == MMG_ACTION_CLOSE) running = 0;
                        fprintf(stdout, "[mmg] action=%d payload=%s\n", (int)ev->action, ev->payload);
                    }
                }
                if (scene.app.enable_runtime_bridge) {
                    for (size_t i = 0; i < scene.bridge_callback_count; ++i) {
                        MMGBridgeCallback* cb = &scene.bridge_callbacks[i];
                        int match = (cb->type == MMG_EVENT_KEY) && ((strcmp(cb->match, "Escape") == 0 && e.key.keysym.sym == SDLK_ESCAPE) || (strcmp(cb->match, "Space") == 0 && e.key.keysym.sym == SDLK_SPACE));
                        if (match) mmg_dispatch_runtime_bridge(&scene, cb);
                    }
                }
            }
        }
        setup_ortho(scene.app.width, scene.app.height, scene.app.camera_x, scene.app.camera_y, scene.app.zoom > 0.f ? scene.app.zoom : 1.f);
        glClearColor(scene.app.clear[0], scene.app.clear[1], scene.app.clear[2], scene.app.clear[3]);
        glClear(GL_COLOR_BUFFER_BIT);
        for (size_t i = 0; i < scene.rect_count; ++i) draw_rect(scene.rects[i].x, scene.rects[i].y, scene.rects[i].w, scene.rects[i].h, scene.rects[i].color);
        for (size_t i = 0; i < scene.circle_count; ++i) draw_circle(&scene.circles[i]);
        for (size_t i = 0; i < scene.line_count; ++i) draw_line(&scene.lines[i]);
        draw_sprite_batches(&scene, &pipe);
        SDL_GL_SwapWindow(window);
        Uint32 elapsed = SDL_GetTicks() - start;
        if (elapsed < frame_ms) SDL_Delay(frame_ms - elapsed);
    }
    for (size_t i = 0; i < scene.texture_count; ++i) if (scene.textures[i].loaded) glDeleteTextures(1, &scene.textures[i].gl_id);
    if (pipe.sprite_vbo) glDeleteBuffers(1, &pipe.sprite_vbo);
    if (pipe.sprite_program) glDeleteProgram(pipe.sprite_program);
    if (pipe.color_program) glDeleteProgram(pipe.color_program);
    SDL_GL_DeleteContext(ctx); SDL_DestroyWindow(window);
#ifdef MMG_HAS_SDL2_IMAGE
    IMG_Quit();
#endif
    SDL_Quit();
    return 0;
}
