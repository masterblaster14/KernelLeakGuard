savedcmd_brd.mod := printf '%s\n'   brd.o | awk '!x[$$0]++ { print("./"$$0) }' > brd.mod
