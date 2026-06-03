cmake_minimum_required(VERSION 3.20)
project(mmg_gpu C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR})
find_package(PkgConfig REQUIRED)
pkg_check_modules(SDL2 REQUIRED sdl2)
find_package(OpenGL REQUIRED)
pkg_check_modules(SDL2_IMAGE QUIET SDL2_image)
add_executable(mmg_gpu
  src/main.c
  src/scene_parser.c
  src/renderer_gl.c
)
target_include_directories(mmg_gpu PRIVATE include ${SDL2_INCLUDE_DIRS})
if(SDL2_IMAGE_FOUND)
  target_compile_definitions(mmg_gpu PRIVATE MMG_HAS_SDL2_IMAGE=1)
  target_include_directories(mmg_gpu PRIVATE ${SDL2_IMAGE_INCLUDE_DIRS})
endif()
target_link_libraries(mmg_gpu PRIVATE ${SDL2_LIBRARIES} OpenGL::GL m)
if(SDL2_IMAGE_FOUND)
  target_link_libraries(mmg_gpu PRIVATE ${SDL2_IMAGE_LIBRARIES})
endif()
target_compile_options(mmg_gpu PRIVATE ${SDL2_CFLAGS_OTHER})
if(WIN32)
  target_link_libraries(mmg_gpu PRIVATE opengl32)
endif()
add_custom_command(TARGET mmg_gpu POST_BUILD
  COMMAND ${CMAKE_COMMAND} -E make_directory "$<TARGET_FILE_DIR:mmg_gpu>/shaders"
  COMMAND ${CMAKE_COMMAND} -E copy_directory "${CMAKE_CURRENT_SOURCE_DIR}/shaders" "$<TARGET_FILE_DIR:mmg_gpu>/shaders"
)
