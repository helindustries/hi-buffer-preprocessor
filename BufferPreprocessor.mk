#  Copyright 2023 Hel Industries, all rights reserved.
#
#  For licensing terms, Please find the licensing terms in the closest
#  LICENSE.txt in this repository file going up the directory tree.
#

# Since we process all buffers for inclusion into TIConstantSpan, we also assume we will only ever deal with
# C++ sources and will not be processing any C-only buffers here. In theory, the buffers themselves could
# be used in C files, this would however require re-definition of the defines for declaring the buffers.
# Since our templates also aim at C++ exclusively, more work would be required to differentiate there as
# well though. Because we don't want to deal with having to update include paths, we are just going to
# generate the buffer files right next to the original files. This requires us to pre-filter the files.
BUFFER_PREPROCESSOR_DIR := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
#SHELL := C:/MinGW/msys/1.0/bin/bash.exe
#$(info SH: $(SH) -> $(SHELL))
#$(info MAKEFILE_LIST: $(MAKEFILE_LIST) -> $(lastword $(MAKEFILE_LIST)) -> $(abspath $(lastword $(MAKEFILE_LIST))) -> $(dir $(abspath $(lastword $(strip $(MAKEFILE_LIST))))))
#$(info BUFFER_PREPROCESSOR_DIR: $(BUFFER_PREPROCESSOR_DIR) -> $(shell echo "This is empty") -> $(shell echo "This is full" | cat))
#$(info MAKE_INC_PATH: $(MAKE_INC_PATH) -> $(call to-make-path,$(MAKE_INC_PATH)) -> $(shell ls --color=never $(MAKE_INC_PATH) 2>/dev/null))
ifneq ($(strip $(PLATFORM_UTILS_PRESENT)),yes)
    # If PLATFORM_UTILS_PRESENT is set, we are building against the makefile-based hybrid build system,
    # otherwise we need to solve a few dependencies here so it is stand-alone.
	include $(BUFFER_PREPROCESSOR_DIR)/PlatformUtils/PlatformUtils.mk
    CFGMSG := printf "    %-30s %s\n"
    MSG := true
    ifneq ($(strip $(PYTHON_ADDITIONAL_PATHS)),)
        PYTHON_PATH := $(call env-paths,$(call shell-list,$(BUFFER_PREPROCESSOR_DIR) $(PYTHON_ADDITIONAL_PATHS)))
        PYTHON_ENV ?= PYTHONPATH="$(PYTHON_PATH)"
    endif
    PYTHON ?= $(PYTHON_ENV) python
endif

BUFFER_PREPROCESSOR := $(BUFFER_PREPROCESSOR_DIR)/dist/$(PLATFORM_ID)/buffer_utility
ifeq ($(call exists,$(BUFFER_PREPROCESSOR)),)
    BUFFER_PROCESSOR_PATH := $(BUFFER_PREPROCESSOR_DIR)/buffer_utility.py

    # Converting the path to shell path here, as it is the last step to the
    # shell command and the Makefile paths don't work as input for Python
    BUFFER_PREPROCESSOR := $(PYTHON) "$(call env-path,$(BUFFER_PROCESSOR_PATH))"
    BUFFER_PREPROCESSOR_MODULES = $(wildcard $(BUFFER_PREPROCESSOR_DIR)/buffer_generator/*.py)
endif

CPP_BUFFER_FILES := $(shell $(BUFFER_PREPROCESSOR) filter $(CPP_FILES) $(CXXFLAGS) $(CPPFLAGS))
HEADER_BUFFER_FILES := $(shell $(BUFFER_PREPROCESSOR) filter $(HEADERS) $(CXXFLAGS) $(CPPFLAGS))
CPP_BUFFER_FILES := $(CPP_BUFFER_FILES:%.cpp=%.Data.h)
HEADER_BUFFER_FILES := $(HEADER_BUFFER_FILES:%.h=%.Data.h)

# Need to add these to the build files, so they actually get recognized as dependencies
HEADERS += $(HEADER_BUFFER_FILES) $(CPP_BUFFER_FILES)
$(foreach path,$(HEADER_BUFFER_FILES) $(CPP_BUFFER_FILES),$(shell grep "// <Incomplete>" $(abspath $(path)) >/dev/null 2>&1 && rm -f $(path)))

buffers: $(CPP_BUFFER_FILES) $(HEADER_BUFFER_FILES) $(BUFFER_PROCESSOR_PATH) $(BUFFER_PREPROCESSOR_MODULES) | silent
	@

clean-buffers: | silent
	$(V)$(RM) $(CPP_BUFFER_FILES) $(HEADER_BUFFER_FILES)

cfg-buffers: | silent
	@$(CFGMSG) "BUFFER_PREPROCESSOR:" "$(BUFFER_PREPROCESSOR)"
	@$(CFGMSG) "CPP_BUFFER_FILES:" "$(CPP_BUFFER_FILES)"
	@$(CFGMSG) "HEADER_BUFFER_FILES:" "$(HEADER_BUFFER_FILES)"
	@$(CFGMSG) "BUFFER_CXXFLAGS:" "$(BUFFER_CXXFLAGS)"
	@$(CFGMSG) "BUFFER_CPPFLAGS:" "$(BUFFER_CPPFLAGS)"

%.Data.h: %.h $(BUFFER_PROCESSOR_PATH) $(BUFFER_PREPROCESSOR_MODULES) $(shell $(BUFFER_PREPROCESSOR) deps $< $(CXXFLAGS) $(CPPFLAGS))
	@$(MSG) "[GEN]" "$(CPU_TARGET)" "$(call env-path,$*.Data.h)";
	$(V)$(BUFFER_PREPROCESSOR) generate $(call env-path,$<) $(call env-path,$@) $(CXXFLAGS) $(CPPFLAGS) > /dev/null

%.Data.h: %.cpp $(BUFFER_PROCESSOR_PATH) $(BUFFER_PREPROCESSOR_MODULES) $(shell $(BUFFER_PREPROCESSOR) deps $< $(CXXFLAGS) $(CPPFLAGS))
	@$(MSG) "[GEN]" "$(CPU_TARGET)" "$(call env-path,$*.Data.h)";
	$(V)$(BUFFER_PREPROCESSOR) generate $(call env-path,$<) $(call env-path,$@) $(CXXFLAGS) $(CPPFLAGS) > /dev/null
