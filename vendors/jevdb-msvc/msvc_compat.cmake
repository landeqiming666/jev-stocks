# The pinned JEVDB Retry-After parser expects a UTC struct tm conversion.
if(MSVC)
  cmake_language(DEFER CALL target_compile_definitions jevdb_loadable_extension PRIVATE timegm=_mkgmtime)
endif()
