# Build the measurement binary ONCE per CPU architecture:   make            (native: x86_64 or aarch64)
#   bin/<arch>/pqcbench      single multi-call executable (tls_probe, tls_serve, tls_load, tls_load_open, tcp_flight)
#   bin/<arch>/hsm_shim.so   LD_PRELOAD shim of the HSM emulation (configured at run time by environment variables)
#   ./tls_probe ... (symlinks in this directory -> bin/<arch>/pqcbench, so that the older scripts keep working)
# The same sources serve both versions: x86-64 (i7-5600U, i5-11500H, i9-10900) and Arm (Cortex-X925, GX10). Code is generic
# (-O2 -mtune=generic): the heavy work is in OpenSSL, which every machine builds for itself (setup_host.sh / portable/setup_x86.sh).
# The binary has no rpath: the OpenSSL to run against is chosen at run time (LD_LIBRARY_PATH=$(PQC_OPENSSL)/lib, done by pqcm.sh),
# so one build serves every OpenSSL of the SAME library soname (libssl.so.3: all 3.x). OpenSSL 4.x has soname libssl.so.4; a binary built
# for 3.x would silently load the SYSTEM libssl.so.3 when LD_LIBRARY_PATH points at a 4.x tree, so 4.x gets its own binary in
# bin/<arch>-ossl4 (chosen automatically from the soname found under $(PQC_OPENSSL)/lib). Rebuild only if a source file changed or the
# OpenSSL headers changed their API.
PQC_OPENSSL ?= $(HOME)/opt/openssl-3.5
ARCH := $(shell uname -m)
SOVER := $(shell ls $(PQC_OPENSSL)/lib/libssl.so.[0-9]* 2>/dev/null | head -1 | sed 's/.*\.so\.//')
SUF  := $(if $(filter-out 3,$(SOVER)),$(if $(SOVER),-ossl$(SOVER)),)
BIN  := bin/$(ARCH)$(SUF)
CC   ?= gcc
CFLAGS ?= -O2 -Wall -mtune=generic
INC  := -I$(PQC_OPENSSL)/include
LIBS := -L$(PQC_OPENSSL)/lib -lssl -lcrypto -lm -pthread
TOOLS := tls_probe tls_serve tls_load tls_load_open tcp_flight bench_pqc tls_client_time
vpath %.c ..

all: $(BIN)/pqcbench $(BIN)/hsm_shim.so links

$(BIN)/%.o: %.c | $(BIN)
	$(CC) $(CFLAGS) $(INC) -pthread -Dmain=$*_main -c -o $@ $<
$(BIN)/pqcbench.o: pqcbench.c | $(BIN)
	$(CC) $(CFLAGS) -c -o $@ $<
$(BIN)/pqcbench: $(BIN)/pqcbench.o $(addprefix $(BIN)/,$(addsuffix .o,$(TOOLS)))
	$(CC) $(CFLAGS) -o $@ $^ $(LIBS)
$(BIN)/hsm_shim.so: hsm_shim.c | $(BIN)
	$(CC) $(CFLAGS) -shared -fPIC -o $@ $< $(INC) -L$(PQC_OPENSSL)/lib -lcrypto -ldl -lpthread -lrt
$(BIN):
	mkdir -p $@
links:
	@for t in $(TOOLS); do ln -sf $(BIN)/pqcbench $$t; done; ln -sf $(BIN)/hsm_shim.so hsm_shim.so
clean:
	rm -rf $(BIN)
.PHONY: all links clean print-bin
print-bin:
	@echo $(BIN)
