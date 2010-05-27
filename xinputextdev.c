/* -*- coding: utf-8 -*-
 * Copyright (C) 2010 The Tegaki project contributors
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License along
 * with this program; if not, write to the Free Software Foundation, Inc.,
 * 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
 *
 * Contributors to this file:
 * - Uli Meis
 */

#include <Python.h>
#include <pygobject.h>
#include <pygtk/pygtk.h>
#include <gtk/gtk.h>
#include <gdk/gdk.h>
#include <gdk/gdkx.h>

#include <X11/Xlib.h>
#include <X11/extensions/XTest.h>
#include <X11/extensions/XInput.h>

#include <pthread.h>

/* enum from linuxwacom's xidump.c */
enum
{
	INPUTEVENT_KEY_PRESS,
	INPUTEVENT_KEY_RELEASE,
	INPUTEVENT_FOCUS_IN,
	INPUTEVENT_FOCUS_OUT,
	INPUTEVENT_BTN_PRESS,
	INPUTEVENT_BTN_RELEASE,
	INPUTEVENT_PROXIMITY_IN,
	INPUTEVENT_PROXIMITY_OUT,
	INPUTEVENT_MOTION_NOTIFY,
	INPUTEVENT_DEVICE_STATE_NOTIFY,
	INPUTEVENT_DEVICE_MAPPING_NOTIFY,
	INPUTEVENT_CHANGE_DEVICE_NOTIFY,
	INPUTEVENT_DEVICE_POINTER_MOTION_HINT,
	INPUTEVENT_DEVICE_BUTTON_MOTION,
	INPUTEVENT_DEVICE_BUTTON1_MOTION,
	INPUTEVENT_DEVICE_BUTTON2_MOTION,
	INPUTEVENT_DEVICE_BUTTON3_MOTION,
	INPUTEVENT_DEVICE_BUTTON4_MOTION,
	INPUTEVENT_DEVICE_BUTTON5_MOTION,

	INPUTEVENT_MAX
};

int inputEventTypes[32] = { 0 };
int devcount = 0;
pthread_t evt;

int x11_fd;
Display *display;
XDevice *xdev;
XDeviceInfoPtr xdevList = NULL;
XDeviceInfoPtr xdevInfo;
XValuatorInfoPtr val = NULL;
int term = FALSE;


XDeviceInfoPtr GetDevice(Display* pDisp, const char* devname)
{
	int i;

	/* get list of devices */
	if (!xdevList)
	{
		xdevList = (XDeviceInfoPtr) XListInputDevices(pDisp, &devcount);
		if (!xdevList)
		{
			fprintf(stderr,"Failed to get input device list.\n");
			return NULL;
		}
	}

	/* find device by name */
	for (i=0; i<devcount; ++i)
	{
		if (!strcasecmp(xdevList[i].name,devname) &&
		    xdevList[i].num_classes)
			return xdevList + i;
	}

	return NULL;
}

#define ASSERTCOND(cond,format,...) if (!(cond)) { \
	fprintf(stderr,format " (at " __FILE__ ",)\n", ##__VA_ARGS__); }

static PyObject * xextdev_init(PyObject *self, PyObject *args)
{
	PyObject *list;
	int i;

	list = PyList_New(0);
	for (i=0; i<devcount; ++i) {
		PyList_Append(list,Py_BuildValue("s",xdevList[i].name));
	}

	term = FALSE;
	return list;
}

static PyObject * xextdev_grab(PyObject *self, PyObject *args)
{
	XEventClass cls;
	const char *devname;
	int devid;
	XAnyClassPtr pClass;
	int j;
	XEventClass eventList[32];
	int nEventListCnt = 0;

	if (!display) {
		ASSERTCOND(display = XOpenDisplay(NULL),"open display");

		/* polling this seems to be the only way 
		* 	 * to do a timed wait on X events */
		x11_fd = ConnectionNumber(display);

		xdevList = (XDeviceInfoPtr) XListInputDevices(display, &devcount);
		if (!xdevList) {
			fprintf(stderr,"Failed to get input device list\n");
			return Py_BuildValue("i", 0);
		}
	}

	if (!PyArg_ParseTuple(args, "i", &devid))
		return Py_BuildValue("i", 0);

	ASSERTCOND(devid<devcount,
		   "Tried to grab non-existing device id %d (max %d)",
		   devid,devcount);

	xdevInfo = xdevList + devid;
	devname = xdevInfo->name;

	val = NULL;

	pClass = xdevInfo->inputclassinfo;
	for (j=0; j<xdevInfo->num_classes; ++j)
	{
		switch (pClass->class) {
		case ValuatorClass:
			val = (XValuatorInfoPtr)pClass;
			break;
		}
		pClass = (XAnyClassPtr)((char*)pClass + pClass->length);
	}

	ASSERTCOND(val,"xinputextdev: Unable to get valuator "
		   "information of '%s'\n",devname);

	/* open device */
	ASSERTCOND(xdev = XOpenDevice(display,xdevInfo->id),
		   "xinputextdev: Unable to open "
		   "input device '%s'\n",devname);

	/* button events */
	DeviceButtonPress(xdev,inputEventTypes[INPUTEVENT_BTN_PRESS],cls);
	if (cls) eventList[nEventListCnt++] = cls;
	DeviceButtonRelease(xdev,inputEventTypes[INPUTEVENT_BTN_RELEASE],cls);
	if (cls) eventList[nEventListCnt++] = cls;

	/* motion events */
	DeviceMotionNotify(xdev,inputEventTypes[INPUTEVENT_MOTION_NOTIFY],cls);
	if (cls) eventList[nEventListCnt++] = cls;

	/* proximity events */
	ProximityOut(xdev,inputEventTypes[INPUTEVENT_PROXIMITY_OUT],cls);
	if (cls) eventList[nEventListCnt++] = cls;
	ProximityIn(xdev,inputEventTypes[INPUTEVENT_PROXIMITY_IN],cls);
	if (cls) eventList[nEventListCnt++] = cls;

	/* grab device */
	int err = XGrabDevice(display,xdev,DefaultRootWindow(display),
			      0,nEventListCnt,eventList,
			      GrabModeAsync,GrabModeAsync,CurrentTime);

	if (err == AlreadyGrabbed)
		fprintf(stderr,"xinputextdev: Grab error: AlreadyGrabbed\n");
	else if (err == GrabNotViewable)
		fprintf(stderr, "xinputextdev: Grab error: GrabNotViewable\n");
	else if (err == GrabFrozen)
		fprintf(stderr, "xinputextdev: Grab error: GrabFrozen\n");
	else {
		printf("xinputextdev: Device '%s' grabbed.\n",devname);
		return Py_BuildValue("[i,i]",
				     val->axes[0].max_value,
				     val->axes[1].max_value);
	}

	return Py_BuildValue("i", 0);
}

Bool predicate( Display *display, XEvent *event, XPointer arg) {
	XDeviceMotionEvent *devev;

	if ((event->type!=inputEventTypes[INPUTEVENT_MOTION_NOTIFY])&&
	    (event->type!=inputEventTypes[INPUTEVENT_BTN_PRESS])&&
	    (event->type!=inputEventTypes[INPUTEVENT_PROXIMITY_OUT])&&
	    (event->type!=inputEventTypes[INPUTEVENT_PROXIMITY_IN])&&
	    (event->type!=inputEventTypes[INPUTEVENT_BTN_RELEASE]))
		return FALSE;

	devev = (XDeviceMotionEvent*)event;

	return devev->deviceid == xdev->device_id;
}

static PyObject * process_event(XEvent *event)
{
	int etype;

	if ((event->type==inputEventTypes[INPUTEVENT_PROXIMITY_OUT])||
	    (event->type==inputEventTypes[INPUTEVENT_PROXIMITY_IN]))
	    {
		XProximityNotifyEvent *pev = (XProximityNotifyEvent*)event;
		if (event->type==inputEventTypes[INPUTEVENT_PROXIMITY_IN])
			etype=3;
		else 
			etype=4;

		return Py_BuildValue("[i,i,i,i,i]",
				     pev->time/1000,
				     etype,
				     pev->axis_data[0],
				     pev->axis_data[1],
				     0);
	}

	if (event->type==inputEventTypes[INPUTEVENT_MOTION_NOTIFY]) {
		XDeviceMotionEvent *mev = (XDeviceMotionEvent*)event;
		return Py_BuildValue("[i,i,i,i,i]",
				     mev->time/1000,
				     0,
				     mev->axis_data[0],
				     mev->axis_data[1],
				     0);
	} else if (
		(event->type==inputEventTypes[INPUTEVENT_BTN_PRESS])||
		(event->type==inputEventTypes[INPUTEVENT_BTN_RELEASE])
		) {
		XDeviceButtonEvent *bev = (XDeviceButtonEvent*)event;
		if (event->type==inputEventTypes[INPUTEVENT_BTN_PRESS])
			etype=1;
		else
		 	etype=2;

		return Py_BuildValue("[i,i,i,i,i]",
				     bev->time/1000,
				     etype,
				     bev->axis_data[0],
				     bev->axis_data[1],
				     bev->button);
	}

	return NULL;
}

static PyObject *xextdev_poll(PyObject *self, PyObject *args)
{
	fd_set in_fds;
	XEvent event;
	struct timeval tv;
	int gotsome = FALSE;

	FD_ZERO(&in_fds);
	FD_SET(x11_fd, &in_fds);
	tv.tv_sec = 1;
	tv.tv_usec = 0;
	PyObject *list = PyList_New(0);

	while(!term) {
		if (XCheckIfEvent(display,&event,predicate,NULL)) {
			do {
				PyObject *py = process_event(&event);
				if (py) {
					PyList_Append(list,py);
					gotsome = TRUE;
				}
			} while (XCheckIfEvent(display,&event,predicate,NULL));
			if (gotsome)
				break;
		}

		Py_BEGIN_ALLOW_THREADS
		select(x11_fd+1, &in_fds, 0, 0, &tv);
		tv.tv_sec = 1;
		tv.tv_usec = 0;
		Py_END_ALLOW_THREADS
	}
	if (term) {
		fprintf(stderr,"Ungrabbing device...\n");
		XUngrabDevice(display,xdev,CurrentTime);
		//while (XPending(display))
		//	XNextEvent(display,&event);
		XCloseDisplay(display);
		display = NULL;
	}

	return list;
}

static PyObject * xextdev_term(PyObject *self, PyObject *args)
{
	term = TRUE;
	return Py_BuildValue("i", 0);
}

static PyMethodDef XInputExtDevMethods[] = {
	{"init", xextdev_init , METH_VARARGS, "Init Device"},
	{"grab", xextdev_grab , METH_VARARGS, "Grab Device"},
	{"poll",  xextdev_poll, METH_VARARGS, "Poll device events"},
	{"term",  xextdev_term, METH_VARARGS, "Term connection"},
	{NULL, NULL, 0, NULL}
};

PyMODINIT_FUNC initxinputextdev(void)
{
	/* Parallel access from here and python/gtk */
	XInitThreads();

	display = XOpenDisplay(NULL);

	/* polling this seems to be the only way 
	 * to do a timed wait on X events */
 	x11_fd = ConnectionNumber(display);

	xdevList = (XDeviceInfoPtr) XListInputDevices(display, &devcount);
	if (!xdevList)
		fprintf(stderr,"Failed to get input device list\n");

	(void) Py_InitModule("xinputextdev", XInputExtDevMethods);
}
