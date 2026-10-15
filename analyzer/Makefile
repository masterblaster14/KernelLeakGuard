# Build klg-analyze against the system LLVM (llvm-dev).
LLVM_CONFIG ?= llvm-config
# make's built-in default (g++) would override "?=", so set it explicitly.
CXX := clang++

CXXFLAGS := $(shell $(LLVM_CONFIG) --cxxflags) -std=c++17 -O2 -g -Wall -fexceptions
LDFLAGS  := $(shell $(LLVM_CONFIG) --ldflags)
LIBS     := $(shell $(LLVM_CONFIG) --link-shared --libs) $(shell $(LLVM_CONFIG) --system-libs)

SRCS := src/main.cpp src/Analyzer.cpp src/Spec.cpp
OBJS := $(patsubst src/%.cpp,build/%.o,$(SRCS))

build/klg-analyze: $(OBJS)
	$(CXX) $(LDFLAGS) -o $@ $^ $(LIBS)

build/%.o: src/%.cpp src/Analyzer.h src/Spec.h | build
	$(CXX) $(CXXFLAGS) -c -o $@ $<

build:
	mkdir -p build

clean:
	rm -rf build

.PHONY: clean
