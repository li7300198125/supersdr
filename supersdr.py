#!/usr/bin/env python3

import pygame
from pygame.locals import *
import pygame, pygame.font, pygame.event, pygame.draw, string, pygame.freetype
from matplotlib import cm
import numpy as np
from scipy import signal

import sys
print (sys.version_info)
if sys.version_info > (3,):
    buffer = memoryview
    def bytearray2str(b):
        return b.decode('ascii')
else:
    def bytearray2str(b):
        return str(b)

import random
import struct
import array
import socket
import time
import math
from datetime import datetime
from collections import deque

from kiwi import wsclient
import mod_pywebsocket.common
from mod_pywebsocket.stream import Stream
from mod_pywebsocket.stream import StreamOptions

from optparse import OptionParser

import pyaudio


# Pyaudio options
FORMAT = pyaudio.paInt16
CHANNELS = 1
AUDIO_RATE = 48000
KIWI_RATE = 12000
SAMPLE_RATIO = int(AUDIO_RATE/KIWI_RATE)
CHUNKS = 16
KIWI_SAMPLES_PER_FRAME = 512
FULL_BUFF_LEN = 20
VOLUME = 100

# Hardcoded values for most kiwis
MAX_FREQ = 30000. # 32000 # this should be dynamically set after connection
MAX_ZOOM = 14.
WF_BINS  = 1024.
DISPLAY_WIDTH = int(WF_BINS)
DISPLAY_HEIGHT = 400
MIN_DYN_RANGE = 70. # minimum visual dynamic range in dB
CLIP_LOWP, CLIP_HIGHP = 40., 100 # clipping percentile levels for waterfall colors
TENMHZ = 10000 # frequency threshold for auto mode (USB/LSB) switch

# Initial KIWI receiver parameters
on=True # AGC auto mode
hang=False # AGC hang
thresh=-75 # AGC threshold in dBm
slope=6 # AGC slope decay
decay=4000 # AGC decay time constant
gain=50 # AGC manual gain
LOW_CUT_SSB=30 # Bandpass low end SSB
HIGH_CUT_SSB=3000 # Bandpass high end
LOW_CUT_CW=300 # Bandpass for CW
HIGH_CUT_CW=800 # High end CW
HIGHLOW_CUT_AM=6000 # Bandpass AM
delta_low, delta_high = 0., 0. # bandpass tuning

# predefined RGB colors
GREY = (200,200,200)
WHITE = (255,255,255)
BLACK = (0,0,0)
D_GREY = (50,50,50)
D_RED = (200,0,0)
D_BLUE = (0,0,200)
D_GREEN = (0,200,0)
RED = (255,0,0)
BLUE = (0,0,255)
GREEN = (0,255,0)
YELLOW = (200,180,0)

# setup colormap from matplotlib
palRGB = cm.jet(range(256))[:,:3]*255

ALLOWED_KEYS = [K_0, K_1, K_2, K_3, K_4, K_5, K_6, K_7, K_8, K_9]
ALLOWED_KEYS += [K_KP0, K_KP1, K_KP2, K_KP3, K_KP4, K_KP5, K_KP6, K_KP7, K_KP8, K_KP9]
ALLOWED_KEYS += [K_BACKSPACE, K_RETURN, K_ESCAPE, K_KP_ENTER]

HELP_MESSAGE_LIST = ["COMMANDS HELP",
        "",
        "- LEFT/RIGHT: move freq +/- 1kHz (+SHIFT: X10)",
        "- PAGE UP/DOWN: move freq +/- 1MHz",
        "- UP/DOWN: zoom in/out by a factor 2X",
        "- U/L/C: switches to USB, LSB, CW",
        "- J/K: change passband (SHIFT inverts increment)",
        "- O: resets passband to defaults",
        "- U/L/C: switches to USB, LSB, CW",
        "- F: enter frequency with keyboard",
        "- V/B: up/down volume 10%",
        "- M: mute/unmute",
        "- S: SMETER show/hide",
        "- X: AUTO MODE ON/OFF (10 MHz mode switch)",
        "- H: displays this help window",
        "- SHIFT+ESC: quits",
        "",
        "",
        "   --- 73 de marco/IS0KYB ---   "]

font_size_dict = {"small": 12, "big": 18}

def get_auto_mode(f):
    return "USB" if f>10000 else "LSB"

def s_meter_draw(rssi_smooth):
    font_size = 8
    smallfont = pygame.freetype.SysFont('Mono', font_size)

    s_meter_radius = 50.
    s_meter_center = (140,s_meter_radius+8)
    alpha_rssi = rssi_smooth+127
    alpha_rssi = -math.radians(alpha_rssi* 180/127.)-math.pi

    def _coords_from_angle(angle, s_meter_radius_):
        x_ = s_meter_radius_ * math.cos(angle)
        y_ = s_meter_radius_ * math.sin(angle)
        s_meter_x = s_meter_center[0] + x_
        s_meter_y = s_meter_center[1] - y_
        return s_meter_x, s_meter_y
    
    s_meter_x, s_meter_y = _coords_from_angle(alpha_rssi, s_meter_radius* 0.95)
    pygame.draw.rect(sdrdisplay, YELLOW,
                   (s_meter_center[0]-60, s_meter_center[1]-58, 2*s_meter_radius+20,s_meter_radius+20), 0)
    pygame.draw.rect(sdrdisplay, BLACK,
                   (s_meter_center[0]-60, s_meter_center[1]-58, 2*s_meter_radius+20,s_meter_radius+20), 3)
    
    angle_list = np.linspace(0.4, math.pi-0.4, 9)
    text_list = ["1", "3", "5", "7", "9", "+10", "+20", "+30", "+40"]
    for alpha_seg, msg in zip(angle_list, text_list[::-1]):
        text_x, text_y = _coords_from_angle(alpha_seg, s_meter_radius*0.8)
        smallfont.render_to(sdrdisplay, (text_x-6, text_y-2), msg, D_GREY)

        seg_x, seg_y = _coords_from_angle(alpha_seg, s_meter_radius)
        color_ =  BLACK
        tick_rad = 2
        if alpha_seg < 1.4:
            color_ = RED
            tick_rad = 3
        pygame.draw.circle(sdrdisplay, color_, (seg_x, seg_y), tick_rad)
    pygame.draw.circle(sdrdisplay, D_GREY, s_meter_center, 4)

    pygame.draw.line(sdrdisplay, BLACK, s_meter_center, (s_meter_x, s_meter_y), 2)
    str_rssi = "%ddBm"%rssi_smooth
    smallfont = pygame.freetype.SysFont('Mono', 10)
    str_len = len(str_rssi)
    pos = (s_meter_center[0]+13, s_meter_center[1])
    smallfont.render_to(sdrdisplay, pos, str_rssi, BLACK)


def change_passband(radio_mode_, delta_low_, delta_high_):
    if radio_mode_ == "USB":
        lc_ = LOW_CUT_SSB+delta_low_
        hc_ = HIGH_CUT_SSB+delta_high_
    elif radio_mode_ == "LSB":
        lc_ = -HIGH_CUT_SSB-delta_high_
        hc_ = -LOW_CUT_SSB-delta_low_
    elif radio_mode_ == "AM":
        lc_ = -HIGHLOW_CUT_AM-delta_high_
        hc_ = HIGHLOW_CUT_AM+delta_high_
    elif radio_mode_ == "CW":
        lc_ = LOW_CUT_CW+delta_low_
        hc_ = HIGH_CUT_CW+delta_high_
    return lc_, hc_


def callback(in_data, frame_count, time_info, status):
    global audio_buffer
#    play_time = CHUNKS * KIWI_SAMPLES_PER_FRAME / AUDIO_RATE
    samples_got = 0
    audio_buf_start_len = len(audio_buffer)
    while audio_buf_start_len+samples_got <= FULL_BUFF_LEN:
        snd_buf = process_audio_stream()
        if snd_buf is not None:
            audio_buffer.append(snd_buf)
            samples_got += 1
        else:
            break
    delta_buff = max(0, FULL_BUFF_LEN - len(audio_buffer))
    #print(FULL_BUFF_LEN, len(audio_buffer), samples_got)

    # emergency buffer fillup with silence
    while len(audio_buffer) <= FULL_BUFF_LEN:
        print("!", end=' ')
        audio_buffer.append(np.zeros((KIWI_SAMPLES_PER_FRAME)))
        
    popped = audio_buffer.pop(0)
    for _ in range(CHUNKS-1):
        popped = np.concatenate((popped, audio_buffer.pop(0)), axis=0)
    popped = popped.astype(np.float64) * (VOLUME/100)
    n = len(popped)
    xa = np.arange(round(n*SAMPLE_RATIO))/SAMPLE_RATIO
    xp = np.arange(n)

    pyaudio_buffer = np.round(np.interp(xa,xp,popped)).astype(np.int16)
    return (pyaudio_buffer, pyaudio.paContinue)

def process_audio_stream():
    global rssi
    data = snd_stream.receive_message()
    if data is None:
        return None
    #flags,seq, = struct.unpack('<BI', buffer(data[0:5]))

    if bytearray2str(data[0:3]) == "SND": # this is one waterfall line
        s_meter, = struct.unpack('>H',  buffer(data[8:10]))
        rssi = 0.1 * s_meter - 127
        data = data[10:]
        count = len(data) // 2
        samples = np.ndarray(count, dtype='>h', buffer=data).astype(np.int16)
        return samples
    else:
        return None

def display_box(screen, message):
    smallfont = pygame.freetype.SysFont('Mono', 12)

    pygame.draw.rect(screen, BLACK,
                   ((screen.get_width() / 2) - 100,
                    (screen.get_height() / 2) - 12,
                    200,18), 0)
    pygame.draw.rect(screen, WHITE,
                   ((screen.get_width() / 2) - 102,
                    (screen.get_height() / 2) - 14,
                    204,20), 1)
    if len(message) != 0:
        pos = ((screen.get_width() / 2) - 70, (screen.get_height() / 2) - 10)
        smallfont.render_to(sdrdisplay, pos, message, WHITE)


def display_help_box(screen, message_list):
    font_size = font_size_dict["small"]
    smallfont = pygame.freetype.SysFont('Mono', font_size)

    window_size = 350
    pygame.draw.rect(screen, (0,0,0),
                   ((screen.get_width() / 2) - window_size/2,
                    (screen.get_height() / 2) - window_size/2,
                    window_size , window_size), 0)
    pygame.draw.rect(screen, (255,255,255),
                   ((screen.get_width() / 2) - window_size/2,
                    (screen.get_height() / 2) - window_size/2,
                    window_size,window_size), 1)

    if len(message_list) != 0:
        for ii, msg in enumerate(message_list):
            pos = (screen.get_width() / 2 - window_size/2 + font_size, 
                    screen.get_height() / 2-window_size/2 + ii*font_size + font_size)
            smallfont.render_to(sdrdisplay, pos, msg, WHITE)

def display_msg_box(screen, message, pos=None, fontsize=12, color=WHITE):
    smallfont = pygame.freetype.SysFont('Mono', fontsize)
    if not pos:
        pos = (screen.get_width() / 2 - 100, screen.get_height() / 2 - 10)
    # pygame.draw.rect(screen, BLACK,
    #                ((screen.get_width() / 2) - msg_len/2,
    #                 (screen.get_height() / 2) - 10, msg_len,20), 0)
    # pygame.draw.rect(screen, WHITE,
    #                ((screen.get_width() / 2) - msg_len/2+2,
    #                 (screen.get_height() / 2) - 12, msg_len+4,24), 1)
    if len(message) != 0:
        smallfont.render_to(sdrdisplay, pos, message, color)

def kiwi_zoom_to_span(zoom):
    """return frequency span in kHz for a given zoom level"""
    assert(zoom >=0 and zoom <= MAX_ZOOM)
    return MAX_FREQ/2**zoom

def kiwi_start_frequency_to_counter(start_frequency_):
    """convert a given start frequency in kHz to the counter value used in _set_zoom_start"""
    assert(start_frequency_ >= 0 and start_frequency_ <= MAX_FREQ)
    counter = round(start_frequency_/MAX_FREQ * 2**MAX_ZOOM * WF_BINS)
    start_frequency_ = counter * MAX_FREQ / WF_BINS / 2**MAX_ZOOM
    return counter, start_frequency_

def kiwi_start_freq(freq, zoom):
    span_khz = kiwi_zoom_to_span(zoom)
    start_freq = freq - span_khz/2
    return start_freq

def kiwi_end_freq(freq, zoom):
    span_khz = kiwi_zoom_to_span(zoom)
    end_freq = freq + span_khz/2
    return end_freq

def kiwi_offset_to_bin(freq, offset_khz, zoom):
    span_khz = kiwi_zoom_to_span(zoom)
    start_freq = freq - span_khz/2
    bins_per_khz = WF_BINS / span_khz
    return bins_per_khz * (offset_khz + span_khz/2)

def kiwi_bins_to_khz(freq, bins, zoom):
    span_khz = kiwi_zoom_to_span(zoom)
    start_freq = freq - span_khz/2
    bins_per_khz = WF_BINS / span_khz
    return (1./bins_per_khz) * (bins) + start_freq

def kiwi_receive_spectrum(wf_data, white_flag=False):
    msg = wf_stream.receive_message()
    if bytearray2str(msg[0:3]) == "W/F": # this is one waterfall line
        msg = msg[16:] # remove some header from each msg
        
        spectrum = np.ndarray(len(msg), dtype='B', buffer=msg).astype(np.float32) # convert from binary data to uint8
        wf = spectrum
        wf = -(255 - wf)  # dBm
        wf_db = wf - 13 # typical Kiwi wf cal
        dyn_range = (np.max(wf_db[1:-1])-np.min(wf_db[1:-1]))
        wf_color =  (wf_db - np.min(wf_db[1:-1]))
        # standardize the distribution between 0 and 1
        wf_color /= np.max(wf_color[1:-1])
        # clip extreme values
        wf_color = np.clip(wf_color, np.percentile(wf_color,CLIP_LOWP), np.percentile(wf_color, CLIP_HIGHP))
        # standardize again between 0 and 255
        wf_color -= np.min(wf_color[1:-1])
        # expand between 0 and 255
        wf_color /= (np.max(wf_color[1:-1])/255.)
        # avoid too bright colors with no signals
        wf_color *= (min(dyn_range, MIN_DYN_RANGE)/MIN_DYN_RANGE)
        # insert a full signal line to see freq/zoom changes
        if white_flag:
            wf_color = np.ones_like(wf_color)*255
        wf_data[-1,:] = wf_color
        wf_data[0:DISPLAY_HEIGHT-1,:] = wf_data[1:DISPLAY_HEIGHT,:]
    
    return wf_data 

def cat_get_freq(cat_socket):
    cat_socket.send("+f\n".encode())
    out = cat_socket.recv(512)
    freq_ = int(out.decode().split(" ")[1].split("\n")[0])/1000.
    return freq_

def cat_get_mode(cat_socket):
    cat_socket.send("m\n".encode())
    out = cat_socket.recv(512)
    radio_mode_ = out.decode().split("\n")[0]
    return radio_mode_

def kiwi_set_freq_zoom(freq_, zoom_, s_):
    start_f_khz_ = kiwi_start_freq(freq_, zoom_)
    end_f_khz_ = kiwi_end_freq(freq_, zoom_)
    if zoom_ == 0:
        print("zoom 0 detected!")
        freq_ = 15000
        start_f_khz_ = kiwi_start_freq(freq_, zoom_)
    else:
        if start_f_khz_<0:
            freq_ -= start_f_khz_
            start_f_khz_ = kiwi_start_freq(freq_, zoom_)

        if end_f_khz_>MAX_FREQ:
            freq_ -= end_f_khz_ - MAX_FREQ
            start_f_khz_ = kiwi_start_freq(freq_, zoom_)
    cnt, actual_freq = kiwi_start_frequency_to_counter(start_f_khz_)
    if zoom_>0 and actual_freq<=0:
        freq_ = kiwi_zoom_to_span(zoom_)
        start_f_khz_ = kiwi_start_freq(freq_, zoom_)
        cnt, actual_freq = kiwi_start_frequency_to_counter(start_f_khz_)
    msg = "SET zoom=%d start=%d" % (zoom_,cnt)
    wf_stream.send_message(msg)
    if s_ and freq_ >= 100:
        s_.send(("F %d\n" % (freq_*1000)).encode())
        out = s_.recv(512).decode()
    return freq_

def kiwi_set_audio_freq(s_, mod_, lc_, hc_, freq_):
    #print(mod_,lc_, hc_)
    msg = 'SET mod=%s low_cut=%d high_cut=%d freq=%.3f' % (mod_, lc_, hc_, freq_)
    snd_stream.send_message(msg)
    
def update_textsurfaces(freq, zoom, radio_mode, rssi, mouse, wf_width):
    global sdrdisplay
    mousex_pos = mouse[0]
    if mousex_pos < 25:
        mousex_pos = 25
    elif mousex_pos >= DISPLAY_WIDTH - 80:
        mousex_pos = DISPLAY_WIDTH - 80

    #           Label   Color   Freq/Mode                       Screen position
    ts_dict = {"freq": (GREEN, "%.2fkHz %s"%(freq, radio_mode), (wf_width/2-60,0), "big", True),
            "left": (GREEN, "%.1f"%(kiwi_start_freq(freq, zoom)) ,(0,0), "small", True),
            "right": (GREEN, "%.1f"%(kiwi_end_freq(freq, zoom)), (wf_width-50,0), "small", True),
            "span": (GREEN, "SPAN %.0fkHz"%(round(kiwi_zoom_to_span(zoom))), (wf_width-180,0), "small", True),
            "filter": (GREEN, "FILT %.1fkHz"%((hc-lc)/1000.), (wf_width-290,0), "small", True),
            "p_freq": (WHITE, "%dkHz"%mouse_khz, (mousex_pos, wf_height-25), "small", True)
    }
    
    draw_dict = {}
    for k in ts_dict:
        if k == "p_freq" and not pygame.mouse.get_focused():
            continue
        if "small" in ts_dict[k][3]:
            smallfont = pygame.freetype.SysFont('Mono', 12)
            render_ = smallfont.render_to
        elif "big" in ts_dict[k][3]:
            bigfont = pygame.freetype.SysFont('Mono', 16)
            render_ = bigfont.render_to
        fontsize_ = font_size_dict[ts_dict[k][3]]

        str_len = len(ts_dict[k][1])
        x_r, y_r = ts_dict[k][2]
        if ts_dict[k][4]:
            pygame.draw.rect(sdrdisplay, D_GREY, (x_r-1, y_r-1, (str_len+0.5)*7, 14), 0)
        render_(sdrdisplay, ts_dict[k][2], ts_dict[k][1], ts_dict[k][0])

def draw_lines(surface, center_freq_bin, freq, wf_height, radio_mode, zoom, mouse):
    pygame.draw.line(surface, RED, (center_freq_bin, 0), (center_freq_bin, wf_height), 2)
    freq_bin = kiwi_offset_to_bin(freq, lc/1000., zoom)
    pygame.draw.line(surface, (0,200,200), (freq_bin, wf_height/20), (freq_bin, wf_height), 1)
    freq_bin = kiwi_offset_to_bin(freq, hc/1000, zoom)
    pygame.draw.line(surface, (0,200,0), (freq_bin, wf_height/20), (freq_bin, wf_height), 1)

    pygame.draw.line(surface, (250,0,0), (mouse[0], wf_height-20), (mouse[0], wf_height), 1)

parser = OptionParser()
parser.add_option("-a", "--audio", type=int,
                  help="KiwiSDR soundstream", dest="kiwi_audio", default=1)
parser.add_option("-w", "--password", type=str,
                  help="KiwiSDR password", dest="kiwi_password", default="")
parser.add_option("-s", "--kiwiserver", type=str,
                  help="KiwiSDR server name", dest="kiwiserver", default='192.168.1.82')
parser.add_option("-p", "--kiwiport", type=int,
                  help="port number", dest="kiwiport", default=8073)
parser.add_option("-S", "--radioserver", type=str,
                  help="RTX server name", dest="radioserver", default=None)
parser.add_option("-P", "--radioport", type=int,
                  help="port number", dest="radioport", default=4532)
parser.add_option("-z", "--zoom", type=int,
                  help="zoom factor", dest="zoom", default=10)
parser.add_option("-f", "--freq", type=int,
                  help="center frequency in kHz", dest="freq", default=14060)
                  
options = vars(parser.parse_args()[0])

# kiwi hostname and port
kiwihost = options['kiwiserver']
kiwiport = options['kiwiport']
kiwi_password = options['kiwi_password']

print ("KiwiSDR Server: %s:%d" % (kiwihost, kiwiport))

#rigctld hostname and port
radiohost = options['radioserver']
radioport = options['radioport']
print ("RTX rigctld server: %s:%d" % (radiohost, radioport))
cat_flag = True
if not radiohost:
    cat_flag = False
# create a socket to communicate with rigctld
if cat_flag:
    cat_socket = socket.socket()
    cat_socket.connect((radiohost, radioport))
    radio_mode = cat_get_mode(cat_socket)
else:
    cat_socket = None
    radio_mode = "USB"

# kiwi RX parameters
zoom = options['zoom']
print ("Zoom factor:", zoom)
freq = options['freq'] # this is the central freq in kHz
start_f_khz = kiwi_start_freq(freq, zoom)
cnt, actual_freq = kiwi_start_frequency_to_counter(start_f_khz)
print ("Actual frequency:", actual_freq, "kHz")

########################## W/F connection
# connect to kiwi server
print ("Trying to contact server...")
try:
    kiwisocket = socket.socket()
    kiwisocket.connect((kiwihost, kiwiport))
except:
    print ("Failed to connect")
    exit()   
print ("Socket open...")

uri = '/%d/%s' % (int(time.time()), 'W/F')
handshake_wf = wsclient.ClientHandshakeProcessor(kiwisocket, kiwihost, kiwiport)
handshake_wf.handshake(uri)
request_wf = wsclient.ClientRequest(kiwisocket)
request_wf.ws_version = mod_pywebsocket.common.VERSION_HYBI13
stream_option_wf = StreamOptions()
stream_option_wf.mask_send = True
stream_option_wf.unmask_receive = False

wf_stream = Stream(request_wf, stream_option_wf)
print ("Waterfall data stream active...")

# send a sequence of messages to the server, hardcoded for now
# max wf speed, no compression
msg_list = ['SET auth t=kiwi p=%s'%kiwi_password, 'SET zoom=%d start=%d'%(zoom,cnt),\
'SET maxdb=0 mindb=-100', 'SET wf_speed=4', 'SET wf_comp=0', 'SET maxdb=-10 mindb=-110']
for msg in msg_list:
    wf_stream.send_message(msg)
print ("Starting to retrieve waterfall data...")

########################### SND connection
# connect to kiwi server
kiwisocket_snd = None
snd_stream = None
kiwi_audio = options["kiwi_audio"]
if kiwi_audio>0:
    print ("Trying to contact server...")
    try:
        kiwisocket_snd = socket.socket()
        kiwisocket_snd.connect((kiwihost, kiwiport))

        uri = '/%d/%s' % (int(time.time()), 'SND')
        handshake_snd = wsclient.ClientHandshakeProcessor(kiwisocket_snd, kiwihost, kiwiport)
        handshake_snd.handshake(uri)
        request_snd = wsclient.ClientRequest(kiwisocket_snd)
        request_snd.ws_version = mod_pywebsocket.common.VERSION_HYBI13
        stream_option_snd = StreamOptions()
        stream_option_snd.mask_send = True
        stream_option_snd.unmask_receive = False
        snd_stream = Stream(request_snd, stream_option_snd)
        print ("Audio data stream active...")
    except:
        print ("Failed to connect")
        exit()   
    print ("Socket open...")

# create a numpy array to contain the waterfall data
wf_data = np.zeros((DISPLAY_HEIGHT, int(WF_BINS)))
lc, hc = change_passband(radio_mode, delta_low, delta_high)

if snd_stream:
    
    msg_list = ["SET auth t=kiwi p=%s"%kiwi_password, "SET mod=%s low_cut=%d high_cut=%d freq=%.3f" %
    (radio_mode.lower(), lc, hc, freq),
    "SET compression=0", "SET ident_user=SuperSDR","SET OVERRIDE inactivity_timeout=1000",
    "SET agc=%d hang=%d thresh=%d slope=%d decay=%d manGain=%d" % (on, hang, thresh, slope, decay, gain),
    "SET AR OK in=%d out=%d" % (KIWI_RATE, AUDIO_RATE)]
    print (msg_list)
    for msg in msg_list:
        snd_stream.send_message(msg)
    time.sleep(0)

# init pygame basic objects
pygame.init()
sdrdisplay = pygame.display.set_mode((DISPLAY_WIDTH, DISPLAY_HEIGHT))
wf_width = sdrdisplay.get_width()
wf_height = sdrdisplay.get_height()

i_icon = "icon.jpg"
icon = pygame.image.load(i_icon)
pygame.display.set_icon(icon)
pygame.display.set_caption("SuperSDR 0.0")
clock = pygame.time.Clock()
pygame.key.set_repeat(200, 200)

wf_quit = False

auto_mode = True
new_freq = freq
input_freq_flag = False
show_help_flag =  False
show_volume_flag =  False
show_automode_flag = False
s_meter_show_flag = True

rssi = 0
question = "Freq (kHz)"
current_string = []

if snd_stream:
    audio_buffer = []
    for k in range(FULL_BUFF_LEN*2):
       snd_stream.send_message('SET keepalive')
       snd_buf = process_audio_stream()
       if snd_buf is not None:
           audio_buffer.append(snd_buf)

    play = pyaudio.PyAudio()
    for i in range(play.get_device_count()):
        #print(play.get_device_info_by_index(i))
        if play.get_device_info_by_index(i)['name'] == "pulse":
            CARD_INDEX = i
        else:
            CARD_INDEX = None

    # open stream using callback (3)
    kiwi_audio_stream = play.open(format=FORMAT,
                    channels=CHANNELS,
                    rate=AUDIO_RATE,
                    output=True,
                    output_device_index=CARD_INDEX,
                    frames_per_buffer=int(KIWI_SAMPLES_PER_FRAME*CHUNKS*SAMPLE_RATIO),
                    stream_callback=callback)


    kiwi_audio_stream.start_stream()

rssi_maxlen = FULL_BUFF_LEN*2
rssi_hist = deque(rssi_maxlen*[rssi], rssi_maxlen)
run_index = 0
run_index_automode = 0
while not wf_quit:
    rssi_hist.append(rssi)
    run_index += 1
    mouse = pygame.mouse.get_pos()
    click_freq = None
    change_zoom_flag = False
    change_freq_flag = False
    change_mode_flag = False
    for event in pygame.event.get():
        if event.type == pygame.KEYDOWN:
            show_help_flag = False
            show_volume_flag = False
            if not input_freq_flag:
                keys = pygame.key.get_pressed()
                shift_mult = 10. if keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT] else 1.
                if zoom>=12:
                    shift_mult /= 10.
                if keys[pygame.K_o]:
                    click_freq = freq
                    delta_low = 0
                    delta_high = 0
                if keys[pygame.K_j]:
                    click_freq = freq
                    delta = -100 if (keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]) else 100
                    delta_low += delta
                    if abs(delta_low) > 3000:
                        delta_low = 3000
                    elif delta_low < -3000:
                        delta_low = 3000
                if keys[pygame.K_k]:
                    click_freq = freq
                    delta = -100 if (keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]) else 100
                    delta_high += delta
                    if abs(delta_high) > 3000:
                        delta_high = 3000
                    elif delta_high < -3000:
                        delta_high = -3000.
                if keys[pygame.K_v]:
                    if VOLUME < 150:
                        VOLUME += 10
                    show_volume_flag = True
                    run_index_volume = run_index
                if keys[pygame.K_b]:
                    if VOLUME > 0:
                        VOLUME -= 10
                    show_volume_flag = True
                    run_index_volume = run_index
                if keys[pygame.K_m]:
                    if VOLUME > 0:
                        VOLUME = 0
                    else:
                        VOLUME = 100
                    show_volume_flag = True
                    run_index_volume = run_index
                if keys[pygame.K_DOWN]:
                    if zoom > 0:
                        zoom -= 1
                        click_freq = freq
                        change_zoom_flag = True
                elif keys[pygame.K_UP]:
                    if zoom < MAX_ZOOM:
                        zoom += 1
                        click_freq = freq
                        change_zoom_flag = True
                elif keys[pygame.K_LEFT]:
                    if not (keys[pygame.K_RCTRL] or keys[pygame.K_LCTRL]):                    
                        if radio_mode!="CW":
                            click_freq = round(freq - 1*shift_mult)
                        else:
                            click_freq = (freq - 0.1*shift_mult)
                elif keys[pygame.K_RIGHT]:
                    if not (keys[pygame.K_RCTRL] or keys[pygame.K_LCTRL]):                    
                        if radio_mode!="CW":
                            click_freq = round(freq + 1*shift_mult)
                        else:
                            click_freq = (freq + 0.1*shift_mult)
                elif keys[pygame.K_PAGEDOWN]:
                    click_freq = freq - 1000
                elif keys[pygame.K_PAGEUP]:
                    click_freq = freq + 1000
                elif keys[pygame.K_u]:
                    auto_mode = False
                    if cat_socket:
                        cat_socket.send("+M USB 2400\n".encode())
                        out = cat_socket.recv(512).decode()
                    else:
                        radio_mode = "USB"
                        change_mode_flag = True
                elif keys[pygame.K_l]:
                    auto_mode = False
                    if cat_socket:
                        cat_socket.send("+M LSB 2400\n".encode())
                        out = cat_socket.recv(512).decode()
                    else:
                        radio_mode = "LSB"
                        change_mode_flag = True
                elif keys[pygame.K_c]:
                    auto_mode = False
                    if cat_socket:
                        cat_socket.send("+M CW 500\n".encode())
                        out = cat_socket.recv(512).decode()
                    else:
                        radio_mode = "CW"
                        change_mode_flag = True
                elif keys[pygame.K_a]:
                    auto_mode = False
                    if cat_socket:
                        cat_socket.send("+M AM 6000\n".encode())
                        out = cat_socket.recv(512).decode()
                    else:
                        radio_mode = "AM"
                        change_mode_flag = True
                elif keys[pygame.K_f]:
                    input_freq_flag = True
                    current_string = []
                elif keys[pygame.K_h]:
                    show_help_flag = True
                elif keys[pygame.K_s]:
                    s_meter_show_flag = False if s_meter_show_flag else True
                elif keys[pygame.K_x]:
                    show_automode_flag = True
                    run_index_automode = run_index
                    auto_mode = False if auto_mode else True
                    click_freq = freq
                elif keys[pygame.K_ESCAPE] and keys[pygame.K_LSHIFT]:
                    wf_quit = True
            else: # manual frequency input
                pygame.key.set_repeat(0, 200) # disabe key repeat
                inkey = event.key
                if inkey in ALLOWED_KEYS:
                    if inkey == pygame.K_BACKSPACE:
                        current_string = current_string[0:-1]
                    elif inkey == pygame.K_RETURN:
                        current_string = "".join(current_string)
                        try:
                            click_freq = int(current_string)
                        except:
                            click_freq = freq
                        input_freq_flag = False
                        pygame.key.set_repeat(200, 200)
                    elif inkey == pygame.K_ESCAPE:
                        input_freq_flag = False
                        pygame.key.set_repeat(200, 200)
                        print("ESCAPE!")
                    else:
                        if len(current_string)<10:
                            current_string.append(chr(inkey))
                display_box(sdrdisplay, question + ": " + "".join(current_string))

        if event.type == pygame.QUIT:
            wf_quit = True
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 4: # mouse scroll up
                if zoom<MAX_ZOOM:
                        zoom += 1
                        click_freq = freq #kiwi_bins_to_khz(freq, mouse[0], zoom)
                        change_zoom_flag = True
            elif event.button == 5: # mouse scroll down
                if zoom>0:
                        zoom -= 1
                        click_freq = freq #kiwi_bins_to_khz(freq, mouse[0], zoom)
                        change_zoom_flag = True
            elif event.button == 1:
                if radio_mode == "CW":
                    freq -= 500./1000 # tune CW signal taking into account cw offset
                click_freq = kiwi_bins_to_khz(freq, mouse[0], zoom)

    if auto_mode and radio_mode != get_auto_mode(freq):
        if freq < TENMHZ:
            radio_mode = "LSB"
            lc, hc = change_passband(radio_mode, delta_low, delta_high)
            if snd_stream:
                kiwi_set_audio_freq(snd_stream, radio_mode.lower(), lc, hc, freq)
        else:
            radio_mode = "USB"
            lc, hc = change_passband(radio_mode, delta_low, delta_high)
            if snd_stream:
                kiwi_set_audio_freq(snd_stream, radio_mode.lower(), lc, hc, freq)
        show_automode_flag = True

    if click_freq or change_zoom_flag:
        freq = kiwi_set_freq_zoom(click_freq, zoom, cat_socket)
        lc, hc = change_passband(radio_mode, delta_low, delta_high)
        if snd_stream:
            kiwi_set_audio_freq(snd_stream, radio_mode.lower(), lc, hc, freq)

    if change_mode_flag:
        lc, hc = change_passband(radio_mode, delta_low, delta_high)
        if snd_stream:
            kiwi_set_audio_freq(snd_stream, radio_mode.lower(), lc, hc, freq)

    if cat_flag:
        new_freq = cat_get_freq(cat_socket)
        radio_mode = cat_get_mode(cat_socket)
        if freq != new_freq:
            freq = new_freq
            freq = kiwi_set_freq_zoom(freq, zoom, cat_socket)
            lc, hc = change_passband(radio_mode, delta_low, delta_high)
            if snd_stream:
                kiwi_set_audio_freq(snd_stream, radio_mode.lower(), lc, hc, freq)

    mouse_khz = kiwi_bins_to_khz(freq, mouse[0], zoom)

    if random.random()>0.95:
        wf_stream.send_message('SET keepalive')
        if snd_stream:
            snd_stream.send_message('SET keepalive')
    

#   plot horiz line to show time of freq change
    wf_data = kiwi_receive_spectrum(wf_data, True if click_freq or change_zoom_flag else False)

    surface = pygame.surfarray.make_surface(wf_data.T)

    surface.set_palette(palRGB)
    center_freq_bin = kiwi_offset_to_bin(freq, 0, zoom)
    
    draw_lines(surface, center_freq_bin, freq, wf_height, radio_mode, zoom, mouse)
    
    sdrdisplay.blit(surface, (0, 0))
    update_textsurfaces(freq, zoom, radio_mode, rssi, mouse, wf_width)

#    draw_textsurfaces(draw_dict, ts_dict, sdrdisplay)
    if input_freq_flag:
        display_box(sdrdisplay, question + ": " + "".join(current_string))
    elif show_help_flag:
        display_help_box(sdrdisplay, HELP_MESSAGE_LIST)
    elif show_volume_flag:
        if run_index - run_index_volume > 20:
            show_volume_flag = False
        vol_color = WHITE if VOLUME <= 100 else RED
        display_msg_box(sdrdisplay, "VOLUME: %d"%(VOLUME)+'%',pos=None, fontsize=40, color=vol_color)
    elif show_automode_flag:
        if run_index - run_index_automode > 20:
            show_automode_flag = False
        else:
            str_auto = "ON" if auto_mode else "OFF"
            display_msg_box(sdrdisplay, "AUTO MODE "+str_auto,pos=None, fontsize=40, color=WHITE)

    if s_meter_show_flag:
        rssi_smooth = np.mean(list(rssi_hist)[15:20])
        s_meter_draw(rssi_smooth)


    pygame.display.update()
    clock.tick(30)
    mouse = pygame.mouse.get_pos()

pygame.quit()
try:
    wf_stream.close_connection(mod_pywebsocket.common.STATUS_GOING_AWAY)
    kiwisocket.close()
except Exception as e:
    print ("exception: %s" % e)
