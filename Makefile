# Copyright 2023 Hel Industries, all rights reserved.
#
# For licensing terms, Please find the licensing terms in the closest
# LICENSE.txt in this repository file going up the directory tree.
#
# This Makefile is meant to be used to build a binary distribution, it is not meant for inclusion
# in a project Makefile for buffer processing. Use BufferPreprocessor.mk for that purpose. This
# also requires the Makefile-based hybrid build system to work properly
#

all: python-exec build-python-timestamps | silent
	@

install: | silent
	@

test: test-python | silent
	@

simulate: | silent
	@

clean: clean-python-exec | silent
	@

cfg: cfg-python | silent
	@

BUILD_DIR ?= $(patsubst %/,%,$(abspath $(shell pwd)/build))

PYTHON_FILES := $(wildcard */*.py */*/*.py */*/*/*.py)
PYTHON_FILES_TIMESTAMP := $(PYTHON_FILES:%.py=$(BUILD_DIR)/%.build)

PYTHON_TARGET = buffer_utility
PYTHON_EXEC_PATHS = ../..
VERBOSE = 1

include ../../../Config/BuildSystem.mk
include $(MAKE_INC_PATH)/Python.mk

build-python-timestamps: $(PYTHON_BUILD_TIMESTAMP)
	@

$(PYTHON_BUILD_TIMESTAMP): $(PYTHON_FILES) build-python
	$(V)$(TOUCH) $@

.PHONY: all install test clean cfg build-python-timestamps
