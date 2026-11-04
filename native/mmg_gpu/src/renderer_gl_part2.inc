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
