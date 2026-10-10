/* Private to the C library: shared between mdgl.c (parse/check) and mdgl_render.c (eval/render). */
#ifndef MDGL_INT_H
#define MDGL_INT_H
#include "mdgl.h"
#include <stdint.h>

int mdgl_i_u8dec(const unsigned char *s, size_t n, uint32_t *r);
size_t mdgl_i_u8enc(uint32_t r, char *o);
const mdgl_value_t *mdgl_i_argv_find(const mdgl_arg_t *a, int n, const char *key);
const mdgl_value_t *mdgl_i_argv_get(const mdgl_arg_t *a, int n, const char *key);
int mdgl_i_number(const mdgl_value_t *v, double *out);
int mdgl_i_number_t(const char *s, size_t n, double *out);
int mdgl_i_angle_deg(const mdgl_value_t *v, double *out);
double mdgl_i_gotime(double v);
int mdgl_i_find_actor(const mdgl_scene_t *sc, const char *name);
long mdgl_i_glyph_count(const char *s, size_t n);
int mdgl_i_is_mark(uint32_t r);

#endif
