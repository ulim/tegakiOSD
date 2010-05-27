BUILD_PATH=build/lib.linux-x86_64-2.6


${BUILD_PATH}/xinputextdev.so: xinputextdev.c
	CFLAGS="-Wall" python setup.py build

run:	${BUILD_PATH}/xinputextdev.so
	PYTHONPATH="${BUILD_PATH}" python tegakiosd.py
