import pytest
import time
import numpy as np
import pyqtgraph as pg

from pyacq import create_manager, NumpyDeviceBuffer
from pyacq.dsp.overlapfiltfilt import OverlapFiltfilt, HAVE_PYOPENCL, sosfiltfilt_engines
from pyacq.viewers.qoscilloscope import QOscilloscope

from pyqtgraph.Qt import QtCore, QtGui
import scipy.signal


nb_channel = 4
sample_rate =1000.
#~ chunksize = 500
chunksize = 100
nloop = 20
overlapsize = 250

length = int(chunksize*nloop)
times = np.arange(length)/sample_rate
buffer = np.random.rand(length, nb_channel) *.3
f1, f2, speed = 20., 60., .05
freqs = (np.sin(np.pi*2*speed*times)+1)/2 * (f2-f1) + f1
phases = np.cumsum(freqs/sample_rate)*2*np.pi
ampl = np.abs(np.sin(np.pi*2*speed*8*times))*.8
buffer += (np.sin(phases)*ampl)[:, None]

buffer = buffer.astype('float32')



stream_spec = dict(protocol='tcp', interface='127.0.0.1', transfermode='sharedarray',
                        sharedarray_shape=(nb_channel, 2048*50), ring_buffer_method = 'double',
                        dtype = 'float32',)

def do_filtertest(engine):
    app = pg.mkQApp()
    
    dev = NumpyDeviceBuffer()
    dev.configure(nb_channel=nb_channel, sample_interval=1./sample_rate, chunksize=chunksize,
                    buffer=buffer)
    dev.output.configure(**stream_spec)
    dev.initialize()
    
    
    f1, f2 = 40., 60.
    
    coefficients = scipy.signal.iirfilter(7, [f1/sample_rate*2, f2/sample_rate*2],
                btype = 'bandpass', ftype = 'butter', output = 'sos')
    
    filter = OverlapFiltfilt()
    filter.configure(coefficients = coefficients, engine=engine, chunksize=chunksize, overlapsize=overlapsize)
    filter.input.connect(dev.output)
    filter.output.configure(**stream_spec)
    filter.initialize()
    
    viewer = QOscilloscope()
    viewer.configure(with_user_dialog=True)
    viewer.input.connect(filter.output)
    viewer.initialize()
    viewer.show()

    viewer2 = QOscilloscope()
    viewer2.configure(with_user_dialog=True)
    viewer2.input.connect(dev.output)
    viewer2.initialize()
    viewer2.show()
    
    viewer2.start()
    viewer.start()
    filter.start()
    dev.start()
    
    
    def terminate():
        dev.stop()
        filter.stop()
        viewer.stop()
        viewer2.stop()
        app.quit()
    
    # start for a while
    timer = QtCore.QTimer(singleShot=True, interval=3000)
    timer.timeout.connect(terminate)
    timer.start()
    
    app.exec_()

def test_sosfilter():
    do_filtertest('scipy')

@pytest.mark.skipif(not HAVE_PYOPENCL, reason='no pyopencl')
def test_openclsosfilter():
    do_filtertest('opencl')



def compare_online_offline_engines():
    #TODO loop over overlapsize
    chunksize = 500
    overlapsize = 250

    if HAVE_PYOPENCL:
        engines = ['scipy', 'opencl',]
    else:
        engines = ['scipy']
    
    dtype = 'float32'
    
    coefficients = scipy.signal.iirfilter(7, [f1/sample_rate*2, f2/sample_rate*2],
                btype = 'bandpass', ftype = 'butter', output = 'sos')
    
    offline_arr =  scipy.signal.sosfilt(coefficients.astype('float32'), buffer.astype('float32'), axis=0, zi=None)
    offline_arr = scipy.signal.sosfilt(coefficients.astype('float32'), offline_arr[::-1, :], axis=0, zi=None)
    offline_arr = offline_arr[::-1, :]
    
    for engine in engines:
        print(engine)
        EngineClass = sosfiltfilt_engines[engine]
        filter_engine = EngineClass(coefficients, nb_channel, dtype, chunksize, overlapsize)
        online_arr = np.zeros_like(offline_arr)
        
        
        for i in range(nloop):
            #~ print(i)
            chunk = buffer[i*chunksize:(i+1)*chunksize:,:]
            pos, chunk_filtered = filter_engine.compute_one_chunk((i+1)*chunksize, chunk)
            if pos is not None:
                online_arr[pos-chunk.shape[0]:pos,:] = chunk_filtered
        
        offline_arr = offline_arr[:-overlapsize, :]
        online_arr = online_arr[:-overlapsize, :]
        
        residual = np.abs((online_arr.astype('float64')-offline_arr.astype('float64'))/np.mean(np.abs(offline_arr.astype('float64'))))
        print(np.max(residual))
        assert np.max(residual)<5e-5, 'online differt from offline'
    
        from matplotlib import pyplot
        fig, ax = pyplot.subplots()
        ax.plot(online_arr[:, 2], color = 'r')
        ax.plot(offline_arr[:, 2], color = 'g')
        fig, ax = pyplot.subplots()
        for c in range(nb_channel):
            ax.plot(residual[:, c], color = 'k')
    pyplot.show()
    
    
    

if __name__ == '__main__':
    #~ test_sosfilter()
    #~ test_openclsosfilter()
    
    compare_online_offline_engines()

 