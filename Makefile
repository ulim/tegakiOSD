BUILD_PATH=build/lib.linux-x86_64-2.6
BUILD_TMP_PATH=build/temp.linux-x86_64-2.6

${BUILD_PATH}/xinputextdev.so: xinputextdev.c Makefile
	CFLAGS="-Wall -g" python setup.py build

run:	${BUILD_PATH}/xinputextdev.so
	PYTHONPATH="${BUILD_PATH}" python tegakiosd.py

gdb:	${BUILD_PATH}/xinputextdev.so
	PYTHONPATH="${BUILD_PATH}" gdb --args python tegakiosd.py

clean:
	rm ${BUILD_PATH}/xinputextdev.so ${BUILD_TMP_PATH}/xinputextdev.o

