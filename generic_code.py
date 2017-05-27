import numpy as np
from netCDF4 import Dataset
from mpi4py import MPI
import dwell.fft as fft
import matplotlib
matplotlib.use('Agg')
import matplotlib.pylab as plt
import matplotlib.colors as colors
from matplotlib.backends.backend_pdf import PdfPages
#import matplotlib.tri as tri
import scipy.integrate as integrate
import scipy.signal as signal
import os
import glob
import sys

matplotlib.rcParams.update({'font.size': 9})

directory = str(sys.argv[1])
call_function = str(sys.argv[2])

def find_ls_idx(ls_arr, ls):
    idx = (np.abs(ls_arr-ls)).argmin() # finding index corresponding to wanted solar long
    assert np.min(np.abs(ls_arr-ls)) < 1, 'Solar Longitude {} not in the file'.format(ls)
    return idx

def martians_month(ls, data):
    temp = []
    for i in np.arange(0, 12):
        idx = np.where((ls>i*30)&(ls<(i+1)*30))[0]
        temp.append(data[idx].mean(axis=0))
    temp = np.array(temp)
    return temp

def martians_year(ls, data):
    #### only looking at "second year"
    idx = np.where(ls==360)[0]
    if idx[0] != 0 and idx.size > 1:
        idx0 = idx[0]
        idx1 = idx[1]
        return data[idx0:idx1]
    elif idx[0] != 0 and idx.size == 1:
        idx1 = idx[0]
        return data[:idx1]
    elif idx[0] == 0:
        idx1 = idx[1]
        idx2 = idx[2]
        return data[idx1:idx2]
        
#    idx0 = idx[0]
#    idx1 = idx[1]
#    
#    idxn = idx[-1]
#    
#    shape = idx1 - idx0
#    shapen = ls.size - idxn
#    
#    if idx0 != 0:
#        zeros_data = np.zeros((shape-idx0, data.shape[1], data.shape[2]))
#        data = np.concatenate((zeros_data, data), axis=0)
#    if shape != shapen:
#        zeros_data = np.zeros((shape-shapen, data.shape[1], data.shape[2]))
#        data = np.concatenate((data, zeros_data), axis=0)
#    data = data.reshape((int(data.shape[0]/shape), shape, data.shape[1], data.shape[2]))
#    return data

def redefine_latField(v):
    temp = np.zeros((52,36))
    for i in np.arange(v.shape[0]):
        for j in np.arange(v.shape[1]-1):
            temp[i,j] = np.mean([v[i,j],v[i,j+1]])
    return temp

def spect_v(ls, data, tstep, lonstep, lowcut, highcut, wave):
    tstep = tstep/1440.
    lowcut = 1/lowcut
    highcut = 1/highcut
    
    padd = np.zeros((data.shape[0], data.shape[1]))
    padd[:data.shape[0], :data.shape[1]] = data
        
    padFFT = np.fft.fftshift(np.fft.fft2(padd))
    c = np.fft.fftshift(np.fft.fftfreq(padFFT.shape[0], tstep))
    waven = np.fft.fftshift(np.fft.fftfreq(padFFT.shape[1], lonstep))*360
    
    idx1 = np.where((abs(c)>lowcut)|(abs(c)<highcut))[0]
#    wave1_idx = np.where((abs(waven)<1.5)|(abs(waven)>2.5))[0]
    idx2 = np.where((abs(c)<0.75)&(abs(c)>0.03))[0]
    
#     set everything that satisfy condition as zero, ie only filtering storm system
    padFFT[idx1] = 0
    if wave:
        wave1_idx= np.where((abs(waven)!=wave))[0]
        padFFT[:,wave1_idx] = 0
    else:
        pass

    filtered2 = np.fft.ifft2(np.fft.ifftshift(padFFT))
    filtered = np.abs(filtered2[:data.shape[0], :data.shape[1]])**2

    temp = filtered.mean(axis=1)
    return np.sqrt(temp)

def zonal_plt_monthly(ydata, ls, data, title, level, cmap):
    fig, axes = plt.subplots(nrows=4, ncols=3, figsize=(14,20))
    for i, ax in enumerate(axes.flat):
        y = ydata[i][4:]
        
        #press2 = zonal_p[i-1].mean(axis=1)
        lat = np.linspace(-90, 90, 36) 
        temp_press = np.linspace(1e-2, 900, ydata[i].shape[0])[4:]
        
        lat, temp_press = np.meshgrid(lat, temp_press)
        
        d = data[i][4:]
        
        im = ax.contourf(lat, y, d, 12, cmap=cmap, extend='both')
        if not np.isnan(d).any():
            ax.contour(lat, y, d, 12, linewidths=0.5, colors='k', extend='both')
        
        ax.set_title(r'{} LS {}-{}'.format((title), (i)*30, (i+1)*30))
        if i in [0,3,6,9]: ax.set_ylabel('Pressure (Pa)')
        if i in [9,10,11]: ax.set_xlabel('Latitude ($^\circ$)')
        ax.set_yscale('log')
        ax.set_ylim([900, 1e-2])
        
#        print ('Saving 1st cool shit')
    fig.colorbar(im, ax=axes.ravel().tolist(), shrink=0.3, orientation='horizontal', pad=0.03)
    plt.savefig(pdFfigures, format='pdf', bbox_inches='tight', dpi=800)

def basemap_plt_monthly(data, ls, title, cmap):
    fig, axes = plt.subplots(nrows=4, ncols=3, figsize=(14,20))
    for i, ax in enumerate(axes.flat):
        d = data[i]
        
        #press2 = zonal_p[i-1].mean(axis=1)
        lat = np.linspace(-90, 90, 36) 
        lon = np.linspace(0, 360, 72)
        
        lon, lat = np.meshgrid(lon, lat)

        im = ax.contourf(lon, lat, d, cmap='viridis')
        if not np.isnan(d).any():
            ax.contour(lon, lat, d, linewidths=0.5, colors='black')
        ax.set_title(r'Avg {} LS {}-{} at 2 Pa'.format((title), (i)*30, (i+1)*30))
        
    fig.colorbar(im, ax=axes.ravel().tolist(), shrink=0.3, orientation='horizontal', pad=0.03)
    plt.savefig(pdFfigures, format='pdf', bbox_inches='tight', dpi=800)
    
def plt_bandpass(directory):
    print ('Looking at data ...')
    data_low = sorted(glob.glob(directory+'*low.npy'))
    temp_low = np.zeros((4,36,223))
    for i, file in enumerate(data_low):
        temp_low[i] = np.load(file)
    
    data_high = sorted(glob.glob(directory+'*high.npy'))
    temp_high = np.zeros((4,36,223))
    for i, file in enumerate(data_high):
        temp_high[i] = np.load(file)
        
    lat = np.linspace(-90,90,36)
    ls = np.linspace(0,360,223)
    ls, lat = np.meshgrid(ls, lat)
    
    print ('Plotting ...')
    level = np.linspace(5,25,6)
    fig, axes = plt.subplots(nrows=4, ncols=2, figsize=(14,18))
    for i, ax in enumerate(axes.flat):
        if i in [0,2,4,6]:
            data = temp_low[int(i/2)]
            im = ax.contourf(ls, lat, data, levels=level, cmap='viridis', extend='both')
            for c in im.collections:
                c.set_edgecolor("face")
            name = data_low[int(i/2)].replace(directory, '').replace('sfc_filtered_', '').replace('.npy','')
            ax.set_title(name)
        else:
            data = temp_high[int((i-1)/2)]
            im = ax.contourf(ls, lat, data, levels=level, cmap='viridis', extend='both')
            for c in im.collections:
                c.set_edgecolor("face")
            name = data_high[int((i-1)/2)].replace(directory, '').replace('sfc_filtered_', '').replace('.npy','')
            ax.set_title(name)
    
    print ('Saving ...')
    fig.colorbar(im, ax=axes.ravel().tolist(), shrink=0.3, pad=0.03, orientation='horizontal')
    plt.savefig(pdFfigures, format='pdf', bbox_inches='tight', dpi=800)

def zonal_avg(filedir):
    print ('Looking at zonal avg')
    ### ls1, ls2 - solar longitude 1, 2 ###
    
    filepath = glob.glob(filedir + '*_temp.npy')[0]
    print (filepath)
    temp = np.load(filepath)
    
    filepath = glob.glob(filedir + '*_u.npy')[0]
    print (filepath)
    u = np.load(filepath)
    
    filepath = glob.glob(filedir + '*_press.npy')[0]
    print (filepath)
    p = np.load(filepath)
        
    filepath = glob.glob(filedir + '*_ls.npy')[0]
    print (filepath)
    ls = np.load(filepath)
    
    p = martians_year(ls, p)
    temp = martians_year(ls, temp)
    u = martians_year(ls, u)
    ls = martians_year(ls, ls)

    zonal_t = martians_month(ls, temp)
    zonal_u = martians_month(ls, u)
    zonal_p = martians_month(ls, p)
    
    print ('Plotting some cool shit')
    print ('Saving 1st shit')
    zonal_plt_monthly(zonal_p, ls, zonal_t, 'Zonal Mean Temp', np.linspace(110,240,14), 'viridis')
    print ('Saving 2nd shit')
    zonal_plt_monthly(zonal_p, ls, zonal_u, 'Zonal Mean Wind', np.linspace(-150,150,16), 'inferno')

def zonal_diff(filedir, var1, var2):
    '''     Use [::2] for visal's simulation
            Use [7::8] for chris' r14p1/dust/L40
            Use [::8] for chris' r14p1dust/L45
    '''
    
    if var1 == '*_t_d.npy': 
        name = 'diff'
        level = np.linspace(-12,24,13)
    else: 
        name = 'avg'
        level = np.linspace(110,240,14)
    print ('Looking at thermal tides')
    
    filepath = glob.glob(filedir + '*_press.npy')[0]
    p = np.load(filepath)[::2]

    filepath = glob.glob(filedir + var1)[0]
    t_d = np.load(filepath)
    
    filepath = glob.glob(filedir + var2)[0]
    t_d_2Pa = np.load(filepath)
    print (t_d_2Pa.shape)
    
    filepath = glob.glob(filedir + '*_ls.npy')[0]
    ls = np.load(filepath)[::2]
    
    filepath = glob.glob(filedir + '*_ls_aux9.npy')
    if filepath:
        filepath = filepath[0]
        ls_aux9 = np.load(filepath)
    
        idx = np.where(ls_aux9[0] == ls)[0]
        ls = ls[idx[0]:]
        p = p[idx[0]:]

    t_d = martians_year(ls, t_d)
    t_d_2Pa = martians_year(ls, t_d_2Pa)
    p = martians_year(ls, p)
    ls = martians_year(ls,ls)

    
#    test_diff = t_d_2Pa.reshape((223,3,36,72)).mean(axis=1)
#    ampl, phase, axis = fft.spec1d(t_d_2Pa, 1/72., use_axes = 2)
#    ampl = ampl
#    phase = phase
#    
#    # stacking the array with the respectful wavenumber
#    test = np.zeros((4,669,36)) # amplitude
#    test2 = np.zeros((4,669,36)) # phase
#    for j in np.arange(0,4):
#        for i in np.arange(0,669):
#            test[j,i] = ampl[i,:,j]
#            test2[j,i] = phase[i,:,j]
#    
#    print ('Plotting some cool shit')
#    print ('Saving 1st cool shit')
#    lat = np.linspace(-90, 90, 36) 
#    ls = np.linspace(0,360, 669)
#    t_lat, t_ls = np.meshgrid(lat, ls)
#    fig, axes = plt.subplots(nrows=2, ncols=2, figsize=(8,8))
#    for i, ax in enumerate(axes.flat):
#        amplitude = test[i]
#        phase = test2[i]
#        im = ax.contourf(t_ls, t_lat, amplitude, cmap='viridis')
#        ax.set_title(r'm = {}'.format(i))
#    fig.colorbar(im, ax=axes.ravel().tolist(), shrink=0.3, orientation='horizontal', pad=0.06)
#    plt.savefig(filedir+'wavenumber_timeseries_tdiff.pdf', bbox_inches='tight', dpi=1200)
    
    zonal_t_d = martians_month(ls, t_d)
    zonal_t_2P = martians_month(ls, t_d_2Pa)
    zonal_p = martians_month(ls, p)
    
    print ('Saving 2nd shit')
    zonal_plt_monthly(zonal_p, ls, zonal_t_d, 'T$_{\mathrm{'+name+'}}$', level, 'viridis')
        
#    print ('Saving 3rd cool shit')
#    basemap_plt_monthly(zonal_t_2P, ls, 'T$_{\mathrm{'+name+'}}$', 'viridis')
    
def msf(filedir):
    print ('Looking at zonal mean meridional function')
    
    filepath = glob.glob(filedir + '*_v.npy')[0]
    v = np.load(filepath)
    
    filepath = glob.glob(filedir + '*_press.npy')[0]
    p = np.load(filepath)
    
    filepath = glob.glob(filedir + '*_ls.npy')[0]
    ls = np.load(filepath)

    p = martians_year(ls, p)
    v = martians_year(ls, v)
    ls = martians_year(ls, ls)
    #np.linspace(0, 360, p.shape[0])
    
    msf = np.zeros((12,52,36))
    p_field = np.zeros((12,52,36))
    for k in np.arange(0, 12):
    
        zonal_v = martians_month(ls, v)[k]
        zonal_p = martians_month(ls, p)[k]
        p_field[k] = zonal_p
        zonal_v = redefine_latField(zonal_v)
        
        lat = np.linspace(-90,90,36)
        a = 3389920.
        g = 3.727
        temp = np.zeros((52,36))
        for j in np.arange(temp.shape[1]):
            temp[::-1,j] = 2*np.pi*(a/g)*np.cos(np.deg2rad(lat[j]))*integrate.cumtrapz(zonal_v[:,j][::-1],zonal_p[:,j][::-1], initial=0)
        msf[k] = temp
    
    norm = matplotlib.colors.Normalize(vmin=-1.,vmax=1.)
    zonal_plt_monthly(p_field, ls, msf, 'Mean Meridional Streamfunction', np.linspace(-1.2e9, 4e9, 12), 'viridis')

class hovmoller:
    def __init__(self, directory, bandpass):
        self.comm = MPI.COMM_WORLD
        self.rank = self.comm.Get_rank()
        self.size = self.comm.Get_size()
        self.bandpass = bandpass
        
        assert 36%self.size == 0, "Number of processes requested ({}) is not divisible by latitudinal bins (36)".format(self.size)
        self.runs = int(36/self.size)
        
        self.__main__(directory)
        
    def __checkBandpass__(self, bandpass):
        if bandpass == 'low':
            lowcut = 1.5 # period
            highcut = 5. 
        if bandpass == 'high':
            lowcut = 5 # period
            highcut = 10. 
        if bandpass == 'none':
            lowcut = 1.5 # period
            highcut = 10. 
        return lowcut, highcut
        
    def __main__(self, filedir):
        
        filepath = glob.glob(filedir + '*4_psfc.npy')[0]
        psfc = np.load(filepath)
        
        filepath = glob.glob(filedir + '*_ls_psfc.npy')[0]
        ls = np.load(filepath)  
        
        psfc = martians_year(ls, psfc)
        ls = martians_year(ls, ls)
        
        sfc_storm = np.zeros((self.size*self.runs, ls.size))
        for i in np.arange(0, self.runs):
            if self.rank == 0: print('Calculating latitudinal bins {}-{}'.format(i*self.size, (i+1)*self.size))
            surface_press = psfc[:, self.rank+(i*self.size), :]
            psfc_temp = surface_press - surface_press.mean(axis=0)
#            surface_press = signal.detrend(surface_press, axis=1, type='constant')
#            surface_press = signal.detrend(surface_press, axis=0, type='constant')
#            psfc_temp = surface_press
            
            wave = 2
            lowcut, highcut = self.__checkBandpass__(bandpass)
            temp = spect_v(ls, psfc_temp,  180., 5., lowcut, highcut, wave)
            
            main = np.array(self.comm.gather(temp, root=0))
            if self.rank == 0:
                sfc_storm[i*self.size: (i+1)*self.size] = main
#                sfc_storm = np.sqrt(np.abs(sfc_storm)*np.sign(sfc_storm))
                
        if self.rank == 0:
#            sfc_storm = np.concatenate((sfc_storm[:,:5184], np.zeros((36, 29)), sfc_storm[:,5184:]), axis=1) 
            sfc_storm_normed = sfc_storm#/sfc_storm[:].max(axis=1)[:, np.newaxis]
            sfc_storm_normed = sfc_storm_normed.reshape((36, 223, 12)).mean(axis = 2) # smoothing out array
            
            lat = np.linspace(-90,90,36)
            ls = np.linspace(0,360,223)
            ls, lat = np.meshgrid(ls, lat)
            filename = directory.replace('./test_data/reduction_','').replace('/','')
            np.save('sfc_filtered_{}_{}.npy'.format(str(filename), str(self.bandpass)), sfc_storm_normed)
            
#            sfc_storm[np.where(sfc_storm>5)] = 0
            print ('Saving plot')
            fig, ax = plt.subplots(nrows=1, ncols=1, figsize=(10,6))
            im = ax.contourf(ls, lat, sfc_storm_normed, cmap='viridis')
            ax.set_ylabel('Latitude')
            ax.set_xlabel('Solar Longitude')
            ax.set_title('Bandpass Filter PSFC')
            fig.colorbar(im, shrink=0.3, orientation='horizontal', pad=0.1)
            plt.savefig(pdFfigures, format='pdf', bbox_inches='tight', dpi=800)

if call_function == 'misc':
    with PdfPages(directory+'figures.pdf') as pdFfigures:
        zonal_avg(directory)
        zonal_diff(directory, '*_t_d.npy', '*_t_d_2Pa.npy')
        zonal_diff(directory, '*_t_a.npy', '*_t_a_2Pa.npy')
if call_function == 'msf':
    with PdfPages(directory+'msf.pdf') as pdFfigures:   
        msf(directory)
if call_function == 'bandpass':
    with PdfPages(directory+'bandpass.pdf') as pdFfigures:
        plt_bandpass(directory)
if call_function == 'hovmoller':
    bandpass = str(sys.argv[3])
    with PdfPages(directory+'hovmoller.pdf') as pdFfigures:
        hovmoller(directory, bandpass)

def net_hr_aer(filename, ls1, ls2):
    nc_file = filename
    data = Dataset(nc_file, mode='r')
    
    hrvis = data.variables['HRAERVIS'][:] # heating rate in visible
    hrir = data.variables['HRAERIR'][:] # heating rate in infrared
    p = data.variables['P'][:] # perturbation pressure
    pb = data.variables['PB'][:] # base state pressure
    ls = data.variables['L_S'][:] # solar longitude
    
    idx1 = find_ls_idx(ls, ls1)
    idx2 = find_ls_idx(ls, ls2)
    
    press = p + pb # pressure

    hrvis_avg = hrvis.mean(axis = 3)[idx1:idx2].mean(axis = 0) # avg in long and solar long 
    hrir_avg = hrir.mean(axis = 3)[idx1:idx2].mean(axis = 0) # avg in long and solar long
    net_ir = hrvis_avg + hrir_avg # net heating rate due to aerosols
    
    press_avg = press.mean(axis = 3).mean(axis = 2)[idx1:idx2].mean(axis = 0) # avg in lat, long and solar long
    
    return net_ir, press_avg