#version 120
attribute vec2 a_pos;
attribute vec2 a_uv;
attribute vec4 a_color;
varying vec2 v_uv;
varying vec4 v_color;
uniform vec2 u_view_size;
void main() {
    vec2 clip = vec2((a_pos.x / u_view_size.x) * 2.0 - 1.0, 1.0 - (a_pos.y / u_view_size.y) * 2.0);
    gl_Position = vec4(clip, 0.0, 1.0);
    v_uv = a_uv;
    v_color = a_color;
}
