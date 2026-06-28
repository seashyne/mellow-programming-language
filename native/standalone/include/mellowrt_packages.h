#ifndef MELLOWRT_PACKAGES_H
#define MELLOWRT_PACKAGES_H

#include <stddef.h>

int mellowrt_package_name_valid(const char *name);
int mellowrt_find_project_root(const char *source_path, char *out, size_t out_size);
int mellowrt_resolve_package_entry(const char *source_path, const char *package_name, char *out, size_t out_size);

#endif
