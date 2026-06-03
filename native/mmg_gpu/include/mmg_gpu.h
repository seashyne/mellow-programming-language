#ifndef MMG_GPU_H
#define MMG_GPU_H

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

#define MMG_MAX_TEXTURES 256
#define MMG_MAX_SPRITES 2048
#define MMG_MAX_RECTS 1024
#define MMG_MAX_CIRCLES 512
#define MMG_MAX_LINES 512
#define MMG_MAX_TEXTS 256
#define MMG_MAX_EVENTS 256
#define MMG_MAX_STATE 256
#define MMG_MAX_SCENES 64
#define MMG_MAX_BATCHES 256
#define MMG_MAX_SHADERS 32
#define MMG_MAX_BRIDGE_CALLBACKS 256

typedef enum { MMG_ACTION_NOOP=0, MMG_ACTION_CLOSE=1, MMG_ACTION_PRINT=2, MMG_ACTION_SET=3, MMG_ACTION_INC=4, MMG_ACTION_TOGGLE=5 } MMGActionType;
typedef enum { MMG_EVENT_KEY=1, MMG_EVENT_MOUSE=2 } MMGEventType;
typedef enum { MMG_STATE_STR=1, MMG_STATE_INT=2, MMG_STATE_FLOAT=3, MMG_STATE_BOOL=4 } MMGStateType;

typedef struct {
    char title[256];
    int width;
    int height;
    float clear[4];
    float camera_x;
    float camera_y;
    float zoom;
    int fps;
    int escape_closes;
    int enable_sprite_batching;
    int enable_shader_pipeline;
    int enable_input_callbacks;
    int enable_state_callbacks;
    int enable_runtime_bridge;
} MMGApp;

typedef struct { char id[128]; char source[512]; unsigned int gl_id; int width; int height; int loaded; } MMGTexture;
typedef struct { char name[64]; char vert_path[512]; char frag_path[512]; } MMGShaderRef;
typedef struct { char id[128]; char texture[128]; float x, y, w, h; float color[4]; } MMGSprite;
typedef struct { char scene_id[128]; char texture[128]; int count; } MMGBatchGroup;
typedef struct { float x,y,w,h; float color[4]; } MMGRect;
typedef struct { float x,y,r; float color[4]; } MMGCircle;
typedef struct { float x1,y1,x2,y2; float color[4]; float width; } MMGLine;
typedef struct { float x,y; int size; float color[4]; char text[256]; } MMGText;
typedef struct { char id[128]; int active; } MMGSceneRef;
typedef struct { MMGStateType type; char key[128]; char value[256]; } MMGStateEntry;
typedef struct { MMGEventType type; char match[64]; MMGActionType action; char payload[256]; } MMGEventBinding;
typedef struct { MMGEventType type; char match[64]; MMGActionType action; char payload[256]; } MMGBridgeCallback;
typedef struct {
    MMGApp app;
    MMGTexture textures[MMG_MAX_TEXTURES]; size_t texture_count;
    MMGShaderRef shaders[MMG_MAX_SHADERS]; size_t shader_count;
    MMGSprite sprites[MMG_MAX_SPRITES]; size_t sprite_count;
    MMGBatchGroup batches[MMG_MAX_BATCHES]; size_t batch_count;
    MMGRect rects[MMG_MAX_RECTS]; size_t rect_count;
    MMGCircle circles[MMG_MAX_CIRCLES]; size_t circle_count;
    MMGLine lines[MMG_MAX_LINES]; size_t line_count;
    MMGText texts[MMG_MAX_TEXTS]; size_t text_count;
    MMGEventBinding events[MMG_MAX_EVENTS]; size_t event_count;
    MMGBridgeCallback bridge_callbacks[MMG_MAX_BRIDGE_CALLBACKS]; size_t bridge_callback_count;
    MMGStateEntry state[MMG_MAX_STATE]; size_t state_count;
    MMGSceneRef scenes[MMG_MAX_SCENES]; size_t scene_count;
} MMGScene;

typedef struct {
    float x, y; float u, v; float r, g, b, a;
} MMGSpriteVertex;

int mmg_parse_scene(const char* path, MMGScene* out_scene);
int mmg_run_scene(const MMGScene* scene);
void mmg_dispatch_runtime_bridge(MMGScene* scene, const MMGBridgeCallback* cb);

#ifdef __cplusplus
}
#endif

#endif
