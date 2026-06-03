#include "mmg_gpu.h"

#include <stdio.h>

int main(int argc, char** argv) {
    if (argc < 2) {
        fprintf(stderr, "usage: mmg_gpu <scene.mmgscene>
");
        return 1;
    }
    MMGScene scene;
    if (mmg_parse_scene_file(argv[1], &scene) != 0) {
        fprintf(stderr, "failed to parse scene file: %s
", argv[1]);
        return 2;
    }
    return mmg_run_scene(&scene);
}
