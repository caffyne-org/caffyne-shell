CC      := gcc
CFLAGS  := -fPIC -Wall -Wextra -O2 -Wno-deprecated-declarations -DGLIB_DISABLE_DEPRECATION_WARNINGS
LIBS    := $(shell pkg-config --cflags --libs gtk+-3.0) -lm

TARGET  := libhacktk.so
SRC     := hacktk.c

all: $(TARGET)

$(TARGET): $(SRC)
	$(CC) $(CFLAGS) -shared -o $@ $< $(LIBS)

clean:
	rm -f $(TARGET)

.PHONY: all clean
