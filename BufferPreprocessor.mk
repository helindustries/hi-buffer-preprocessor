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
BUFFER_PREPROCESSOR_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
ifeq ($(strip $(shell ls --color=never $(MAKE_INC_PATH) 2>/dev/null)),)
    # Lets add these, so the makefile can be used standalone
    CFGMSG := printf "    %-30s %s\n"
    MSG := /usr/bin/true
    ifneq ($(strip $(PYTHON_ADDITIONAL_PATHS)),)
        PYTHON_ENV ?= PYTHONPATH="$(PYTHON_ADDITIONAL_PATHS)"
    endif
    PYTHON = $(PYTHON_ENV) python
endif

BUFFER_PREPROCESSOR := $(BUFFER_PREPROCESSOR_DIR)/bin/buffer_utility
ifeq ($(strip $(shell ls --color=never $(BUFFER_PREPROCESSOR) 2>/dev/null)),)
    BUFFER_PROCESSOR_PATH := $(BUFFER_PREPROCESSOR_DIR)/buffer_utility.py
    PYTHON_ADDITIONAL_PATHS := $(BUFFER_PREPROCESSOR_DIR):$(FRAMEWORK_PATH)/Tools/PytonUtilities:$(FRAMEWORK_PATH)
    ifneq ($(strip $(shell ls --color=never $(MAKE_INC_PATH) 2>/dev/null)),)
        ifeq ($(strip $(filter $(MAKE_INC_PATH)/Python.mk,$(MAKEFILE_LIST))),)
            include $(MAKE_INC_PATH)/Python.mk
        endif
    endif

    BUFFER_PREPROCESSOR := $(PYTHON) $(BUFFER_PROCESSOR_PATH)
endif

CPP_BUFFER_FILES := $(shell $(BUFFER_PREPROCESSOR) filter $(CPP_FILES) $(CXXFLAGS) $(CPPFLAGS))
HEADER_BUFFER_FILES := $(shell $(BUFFER_PREPROCESSOR) filter $(HEADERS) $(CXXFLAGS) $(CPPFLAGS))
CPP_BUFFER_FILES := $(CPP_BUFFER_FILES:%.cpp=%.Data.h)
HEADER_BUFFER_FILES := $(HEADER_BUFFER_FILES:%.h=%.Data.h)

# Need to add these to the build files, so they actually get recognized as dependencies
HEADERS += $(HEADER_BUFFER_FILES) $(CPP_BUFFER_FILES)

buffers: $(CPP_BUFFER_FILES) $(HEADER_BUFFER_FILES) $(BUFFER_PROCESSOR_PATH) | silent
	@

clean-buffers: | silent
	$(V)rm -f $(CPP_BUFFER_FILES) $(HEADER_BUFFER_FILES)

cfg-buffers: | silent
	@$(CFGMSG) "BUFFER_PREPROCESSOR:" "$(BUFFER_PREPROCESSOR)"
	@$(CFGMSG) "CPP_BUFFER_FILES:" "$(CPP_BUFFER_FILES)"
	@$(CFGMSG) "HEADER_BUFFER_FILES:" "$(HEADER_BUFFER_FILES)"
	@$(CFGMSG) "BUFFER_CXXFLAGS:" "$(BUFFER_CXXFLAGS)"
	@$(CFGMSG) "BUFFER_CPPFLAGS:" "$(BUFFER_CPPFLAGS)"

%.Data.h: %.h $(BUFFER_PREPROCESSOR) $(shell $(BUFFER_PREPROCESSOR) deps $< $(CXXFLAGS) $(CPPFLAGS))
	@$(MSG) "[GEN]" "$(MCU_TARGET)" "$*.Data.h";
	$(V)$(BUFFER_PREPROCESSOR) generate $< $@ $(CXXFLAGS) $(CPPFLAGS) > /dev/null

%.Data.h: %.cpp $(BUFFER_PREPROCESSOR) $(shell $(BUFFER_PREPROCESSOR) deps $< $(CXXFLAGS) $(CPPFLAGS))
	@$(MSG) "[GEN]" "$(MCU_TARGET)" "$*.Data.h";
	$(V)$(BUFFER_PREPROCESSOR) generate $< $@ $(CXXFLAGS) $(CPPFLAGS) > /dev/null
