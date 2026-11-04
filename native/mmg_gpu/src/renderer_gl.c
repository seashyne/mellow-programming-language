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

#include "renderer_gl_part1.inc"
#include "renderer_gl_part2.inc"
