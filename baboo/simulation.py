import sdeint
import matplotlib.pyplot as plt
import logging
import numpy as np
from tqdm import tqdm

def two_component_fake_data(times, Omgc_start=100,
                            xi_c=1e-11, xi_s=1e-11,
                            N_c=1e-11, N_s=-1e-11,
                            tau_c=1e6, tau_s=3e6,
                            R_c=1e-12, R_s=1e-12):
    """
    Simulate a list of time-ordered frequencies from the two
    component neutron star model with simulated process and
    measurement noise.

    Parameters:
    -----------
    times : np.ndarray
        list of times (in units of seconds)
    Omgc_start : float
        start frequency
    xi_c : float
        crust noise amplitude
    xi_s : float
        superfluid noise amplitude
    N_c : float
        crust torque
    N_s : float
        superfluid torque
    tau_c : float
        crust relaxation time
    tau_s : float
        superfluid relaxation time
    R_c : float
        measurement covariance for crust measurements.
    R_s : float
        measurement covariance for superfluid measurements.
    """
    tau = (tau_c * tau_s) / (tau_c + tau_s)
    # get start for omega_s
    Omgs_start = Omgc_start - (N_c - N_s) * tau
    # define helper functions for sdeint
    F_int = np.longdouble(np.array([[-1/tau_c, 1/tau_c],[1/tau_s, -1/tau_s]]))
    N = np.longdouble(np.array([N_c, N_s]))
    xi = np.longdouble(np.diag([xi_c, xi_s]))
    def f(x, t):
        return F_int.dot(x) + N
    def g(x, t):
        return xi
    states = sdeint.itoint(f, g, np.array([Omgc_start, Omgs_start]), times)
    data = states.copy()
    data[:, 0] += np.random.randn(times.size) * np.sqrt(R_c)
    data[:, 1] += np.random.randn(times.size) * np.sqrt(R_s)
    return data

def freq_fake_data(times,Ndot,
                   f0,fdot0,
                   xi_f, xi_fdot,
                   R):
    """""
    Parameters:
    -----------
    """""
    #Functions for sdeint
    F_int = np.longdouble(np.array([[0,1],[0,0]]))
    N = np.longdouble(np.array([0,Ndot]))
    xi = np.longdouble(np.diag([xi_f,xi_fdot]))
    def f(x,t):
        return F_int.dot(x) + N
    def g(x,t):
        return xi
    states=sdeint.itoint(f,g,np.array([f0,fdot0]),times)
    data=states.copy()
    data[:,0] += np.random.randn(times.size)*np.sqrt(R)
    data[:,1] += np.random.randn(times.size)*np.sqrt(R)
    return data

class SimulationModel(object):
    """base class for a model that we might want to simulate"""
    nstates = 0
    def __init__(self, skipsize=1000):
        super(SimulationModel, self).__init__()

    def expectation(self):
        pass

    def variance(self):
        pass

    def integrate(self, tstarts, toa_errors=None, p0=None, nphase_states=1):
        """
        tstarts : `numpy.ndarray`
            list of MJD times
        """
        # error checking
        if p0 is None:
            raise ValueError("Must supply starting point")

        if toa_errors is None:
            logging.info('toa errors not set. auto setting to a microsecond')
            toa_errors = 1e-6 * np.ones(tstarts.size)
        if np.size(tstarts) != np.size(toa_errors):
            raise ValueError(f'toa size {tstarts.size} and toa error size {toa_errors.size} arrays must be the same length')

        # track first TOA
        pets0 = tstarts[0]

        tstarts = np.round((tstarts - tstarts[0]) * 86400)
        # reset to zero for integration
        # track states that are not the phase
        states_vs_time = np.zeros((np.size(p0) - nphase_states, tstarts.size))

        # set up preliminaries
        prev_tstart = 0
        toa_fracs = [0]
        toa_ints = [0]
        # p0 = np.asarray([phi0, omgc0, omgs0])
        previous_time = toa_fracs[0]
        toa_counter = 0
        states_vs_time[:, 0] = p0[nphase_states:]
        for ii in range(nphase_states):
            p0[ii] = 0. # must be zero at starting time because phase is zero here.
        p0 = np.longdouble(p0)
        for next_tstart,terr in tqdm(zip(tstarts[1:], toa_errors[1:]), total=tstarts.size - 1):
            # start at last tao
            # move to observing time
            # if next toa is at same time as current toa no need to integrate. we
            # just add a new one with different measurement noise.
            if not next_tstart == prev_tstart:
                times = np.arange(0, min(self.skipsize, next_tstart - previous_time), dtype=np.longdouble) + previous_time
                counter = 0
                while np.floor(next_tstart) - times[-1] >= 1:
                    # if first time, don't increment times
                    if counter > 0:
                        # add at most 10 seconds
                        times = np.linspace(times[-1], times[-1] + min(self.skipsize, next_tstart - times[-1]), num=3)
                    counter += 1
                    states = sdeint.itoint(self.expectation, self.variance, np.longdouble(p0), np.longdouble(times))
                    # reset start points
                    p0 = states[-1, :]
                    # wrap phase
                    # raise ValueError('junk')
                    # print(p0)
                    for ii in range(nphase_states):
                        p0[ii] = p0[ii] - np.floor(p0[ii])
            else:
                print('toas are close')
            previous_time = np.longdouble(times[-1])

            # how far from next integer time are we?
            xtra_time  = np.longdouble(1 - p0[0]) / np.longdouble(p0[1])

            # integrate twice as far as that in time.
            newtimes = np.linspace(0, xtra_time, num=int(3))

            # get states at time of TOA
            states_toa = sdeint.itoint(self.expectation, self.variance, p0, newtimes)
            # set TOA
            toa = previous_time + xtra_time # + np.random.randn()*terr
            toa_fracs.append(toa - np.trunc(toa))
            toa_ints.append(np.trunc(toa))

            # track other states
            states_vs_time[:, toa_counter + 1] = states_toa[-1, nphase_states:]
            prev_tstart = next_tstart
            toa_counter += 1
        toa_ints = np.asarray(toa_ints)
        toa_fracs = np.asarray(toa_fracs)
        toa_start = toa_ints[0]
        toa_ints -= toa_start

        toa_fracs += np.random.randn(toa_fracs.size) * toa_errors
        # change back to MJD
        toas = np.longdouble(toa_ints / 86400) + np.longdouble(toa_fracs / 86400)
        # set start time
        toas += pets0
        return toas, toa_errors, states_vs_time

    def integrate_and_return_frequencies(self, tstarts, F0, F1, PEPOCH,
            toa_errors=None, p0=None, Ntoas_per_fit=3, nphase_states=1):
        from .utils import fit_toas_to_get_frequencies
        toas, toa_errors, states = self.integrate(tstarts,
                toa_errors=toa_errors, p0=p0, nphase_states=nphase_states)
        freqs, freqs_errs, times_fit = fit_toas_to_get_frequencies(toas, toa_errors, F0, F1, PEPOCH, Ntoas_per_fit=Ntoas_per_fit)
        return toas, toa_errors, times_fit, freqs, freqs_errs, states


class TwoComponentModelSim(SimulationModel):
    """docstring for TwoComponentModel"""
    nstates = 3
    def __init__(self, r=None, tau=None, omgc_dot=None, lag=None, Qc=None,
            Qs=None, skipsize=1000):
        super(TwoComponentModelSim, self).__init__()
        self.r = r
        self.tau = tau
        self.omgc_dot = omgc_dot
        self.lag = lag
        self.Qc = Qc
        self.Qs = Qs
        self.skipsize=skipsize

        def param_map(A, B, C, D):
            """
            A = r
            B = tau
            C = lag
            D = omgc_dot
            """
            taus = (1+A) * B
            tauc = (1+A) / A * B
            Nc = (D + A/(1+A) * C/B)
            Ns = D - C/B * (1+A)**-1
            return tauc, taus, Nc, Ns
        tauc, taus, Nc, Ns = param_map(self.r, self.tau, self.lag, self.omgc_dot)

        # set up matrices
        # states are [crust phase, crust frequency, superfluid frequency]
        self.F = np.longdouble(np.array([[0., 1., 0.], [0., -1./tauc, 1./tauc],
            [0., 1./taus, -1./taus]]))
        self.N = np.longdouble(np.array([0., Nc, Ns]))
        self.Q = np.longdouble(np.diag([0., np.sqrt(self.Qc),
            np.sqrt(self.Qs)]))

        # self.F = np.array([[0., 0., 1., 0.], [0., 0., 0., 1.], [0., 0., -1./tauc, 1./tauc], [0., 0., 1./taus, -1./taus]])
        # self.N = np.array([0., 0., Nc, Ns])
        # self.Q = np.diag([0.,0.,  np.sqrt(self.Qc), np.sqrt(self.Qs)])

    def expectation(self, x, t):
        return self.F @ x + self.N

    def variance(self, x, t):
        return self.Q

    def __call__(self, times, p0, toa_errors=None):
        return self.integrate(times, p0=p0, toa_errors=toa_errors, nphase_states=1)

class OneComponentModelSim(SimulationModel):
    """One component model simulation"""
    nstates = 3
    def __init__(self, F2=0, Q_f=0,
            Q_f1=None, Q_f2=0, skipsize=1000):
        super(OneComponentModelSim, self).__init__()
        self.F2 = F2
        self.Q_f = Q_f
        if Q_f1 is None:
            raise ValueError('Must specify noise on frequency derivatives')
        self.Q_f1 = Q_f1
        self.Q_f2 = Q_f2
        self.skipsize=1000

        # set up matrices
        # states are [crust phase, crust frequency, superfluid frequency]
        self.F = np.longdouble(np.array([[0, 1, 0], [0, 0, 1], [0, 0, 0]]))
        self.N = np.longdouble(np.array([0, 0, self.F2]))
        self.Q = np.longdouble(np.diag([np.sqrt(Q_f), np.sqrt(Q_f1), np.sqrt(Q_f2)]))

    def expectation(self, x, t):
        return self.F @ x + self.N

    def variance(self, x, t):
        return self.Q

    def __call__(self, times, p0, toa_errors=None):
        """
        times : `numpy.ndarray`
            List of times [mjd] at which to evaluate this.
        p0 : `numpy.ndarray`
            [initial phase, initial frequency, initial frequency derivative]
        toa_errors : `numpy.ndarray`
            Errors on output TOAs to give. Default = 1e-6 seconds.
        """
        return self.integrate(times, p0=p0, toa_errors=toa_errors)
