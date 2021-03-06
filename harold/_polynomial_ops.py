"""
The MIT License (MIT)

Copyright (c) 2016 Ilhan Polat

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""

import numpy as np
import collections
from scipy.signal import deconvolve
from scipy.linalg import block_diag, lu
from ._aux_linalg import haroldsvd, e_i

__all__ = ['haroldlcm', 'haroldgcd', 'haroldcompanion', 'haroldtrimleftzeros',
           'haroldpoly', 'haroldpolyadd', 'haroldpolymul', 'haroldpolydiv']


def haroldlcm(*args, compute_multipliers=True, cleanup_threshold=1e-9):
    """
    Takes n-many 1D numpy arrays and computes the numerical
    least common multiple polynomial. The polynomials are
    assumed to be in decreasing powers, e.g. s^2 + 5 should
    be given as numpy.array([1,0,5])

    Returns a numpy array holding the polynomial coefficients
    of LCM and a list, of which entries are the polynomial
    multipliers to arrive at the LCM of each input element.

    For the multiplier computation, a variant of Karcanias, Mitrouli,
    *System theoretic based characterisation and computation of the
    least common multiple of a set of polynomials*, Lin Alg App, 381, 2004,
    is used.

    Parameters
    ----------
    args : 1D Numpy array
    compute_multipliers : boolean, optional
        After the computation of the LCM, this switch decides whether the
        multipliers of the given arguments should be computed or skipped.
        A multiplier in this context is ``[1,3]`` for the argument ``[1,2]``
        if the LCM turns out to be ``[1,5,6]``.
    cleanup_threshold : float
        The computed polynomials might contain some numerical noise and after
        finishing everything this value is used to clean up the tiny entries.
        Set this value to zero to turn off this behavior. The default value
        is :math:`10^{-9}`.

    Returns
    --------
    lcmpoly : 1D Numpy array
        Resulting polynomial coefficients for the LCM.
    mults : List of 1D Numpy arrays
        The multipliers for each given argument.

    Example
    -------
    ::

        >>>> a , b = haroldlcm(*map(np.array,
                                    ([1,3,0,-4],
                                    [1,-4,-3,18],
                                    [1,-4,3],
                                    [1,-2,-8])))
        >>>> a
            (array([   1.,   -7.,    3.,   59.,  -68., -132.,  144.])

        >>>> b
            [array([  1., -10.,  33., -36.]),
             array([  1.,  -3.,  -6.,   8.]),
             array([  1.,  -3., -12.,  20.,  48.]),
             array([  1.,  -5.,   1.,  21., -18.])]

        >>>> np.convolve([1,3,0,-4],b[0]) # or haroldpolymul() for poly mult
            (array([   1.,   -7.,    3.,   59.,  -68., -132.,  144.]),

    """
    # As typical, it turns out that the minimality and c'ble subspace for
    # this is done already (Karcanias, Mitrouli, 2004). They also have a
    # clever extra step for the multipliers thanks to the structure of
    # adjoint which I completely overlooked.
    if not all([isinstance(x, type(np.array([0]))) for x in args]):
        raise TypeError('Some arguments are not numpy arrays for LCM')

    # Remove if there are constant polynomials but return their multiplier!
    poppedargs = tuple([x for x in args if x.size > 1])
    # Get the index number of the ones that are popped
    poppedindex = tuple([ind for ind, x in enumerate(args) if x.size == 1])
    a = block_diag(*tuple(map(haroldcompanion, poppedargs)))  # Companion A
    b = np.concatenate(tuple(map(lambda x: e_i(x-1, -1),
                                 [z.size for z in poppedargs])))  # Companion B
    c = block_diag(*tuple(map(lambda x: e_i(x-1, 0).T,
                              [z.size for z in poppedargs])))
    n = a.shape[0]

    # TODO: Below two lines feel like matlab programming, revisit again
    C = b
    i = 1
    # Computing full c'bility matrix is redundant we just need to see where
    # the rank drop is (if any!).
    # Also due matrix power, things grow too quickly.
    while np.linalg.matrix_rank(C) == C.shape[1] and i <= n:
        C = np.hstack((C, np.linalg.matrix_power(a, i).dot(b)))
        i += 1
    s, v = haroldsvd(C)[1:]
    temp = s.dot(v)
    # If not coprime we should "expect" zero rows at the bottom

    if i-1 == n:  # Relatively coprime
        temp2 = np.linalg.inv(temp[:, :-1])  # Every col until the last
    else:
        temp2 = block_diag(np.linalg.inv(temp[:i-1, :i-1]), np.eye(n+1-i))

    lcmpoly = temp2.dot(-temp)[:i-1, -1]
    # Add monic coefficient and flip
    lcmpoly = np.append(lcmpoly, 1)[::-1]

    if compute_multipliers:
        a_lcm = haroldcompanion(lcmpoly)
        b_lcm = np.linalg.pinv(C[:c.shape[1], :-1]).dot(b)
        c_lcm = c.dot(C[:c.shape[1], :-1])

        # adj(sI-A) formulas with A being a companion matrix
        # We need an array container so back to list of lists
        n_lcm = a_lcm.shape[0]
        # Create a list of lists of lists with zeros
        adjA = [[[0]*n_lcm for m in range(n_lcm)] for n in range(n_lcm)]

        # looping fun
        for x in range(n_lcm):
            # Diagonal terms
            adjA[x][x][:n_lcm-x] = list(lcmpoly[:n_lcm-x])
            for y in range(n_lcm):
                if y < x:  # Upper Triangular terms
                    adjA[y][x][x-y:] = adjA[x][x][:n_lcm-(x-y)]
                elif y > x:  # Lower Triangular terms
                    adjA[y][x][n_lcm-y:n_lcm+1-y+x] = list(
                                                        -lcmpoly[-x-1:n_lcm+1])

        """
        Ok, now get C_lcm * adj(sI-A_lcm) * B_lcm

        Since we are dealing with lists we have to fake a matrix multiplication
        with an evil hack. The reason is that, entries of adj(sI-A_lcm) are
        polynomials and numpy doesn't have a container for such stuff hence we
        store them in Python "list" objects and manually perform elementwise
        multiplication.

        Middle three lines take the respective element of b vector and
        multiplies the column of list of lists. Hence we actually obtain

                    adj(sI-A_lcm) * blockdiag(B_lcm)

        The resulting row entries are added to each other to get
        adj(sI-A)*B_lcm. Finally, since we now have a single column we can
        treat polynomial entries as matrix entries hence multiplied with c
        matrix properly.

        """
        mults = c_lcm.dot(
            np.vstack(
                tuple(
                    [haroldpolyadd(*w, trimzeros=False) for w in
                        tuple(
                            [
                              [
                                [b_lcm[y, 0]*z for z in adjA[y][x]]
                                for y in range(n_lcm)] for x in range(n_lcm)
                            ]
                          )
                     ]
                 )
                 )
               )

        # If any reinsert lcm polynomial for constant polynomials
        if not poppedindex == ():
            dummyindex = 0
            dummymatrix = np.zeros((len(args), lcmpoly.size))
            for x in range(len(args)):
                if x in poppedindex:
                    dummymatrix[x, :] = lcmpoly
                    dummyindex += 1
                else:
                    dummymatrix[x, 1:] = mults[x-dummyindex, :]
            mults = dummymatrix

        lcmpoly[abs(lcmpoly) < cleanup_threshold] = 0.
        mults[abs(mults) < cleanup_threshold] = 0.
        mults = [haroldtrimleftzeros(z) for z in mults]
        return lcmpoly, mults
    else:
        return lcmpoly


def haroldgcd(*args):
    """
    Takes 1D numpy arrays and computes the numerical greatest common
    divisor polynomial. The polynomials are assumed to be in decreasing
    powers, e.g. :math:`s^2 + 5` should be given as ``numpy.array([1,0,5])``.

    Returns a numpy array holding the polynomial coefficients
    of GCD. The GCD does not cancel scalars but returns only monic roots.
    In other words, the GCD of polynomials :math:`2` and :math:`2s+4` is
    still computed as :math:`1`.

    Parameters
    ----------
    args : 1D Numpy arrays

    Returns
    --------

    gcdpoly : 1D Numpy array

    Example
    -------

    ::

        >>>> a = haroldgcd(*map(haroldpoly,([-1,-1,-2,-1j,1j],
                                            [-2,-3,-4,-5],
                                            [-2]*10)))
        >>>> a
             array([ 1.,  2.])


    .. warning:: It uses the LU factorization of the Sylvester matrix.
                 Use responsibly. It does not check any certificate of
                 success by any means (maybe it will in the future).
                 I have played around with ERES method but probably due
                 to my implementation, couldn't get satisfactory results.
                 Hence I've switched to matrix-based methods. I am still
                 interested in better methods though, so please contact
                 me if you have a working implementation that improves
                 over this.

    """
    if not all([isinstance(x, type(np.array([0]))) for x in args]):
        raise TypeError('Some arguments are not numpy arrays for GCD')

    not_1d_err_msg = ('GCD computations require explicit 1D '
                      'numpy arrays or\n2D but having one of '
                      'the dimensions being 1 e.g., (n,1) or (1,n)\narrays.')
    try:
        regular_args = [haroldtrimleftzeros(
                            np.atleast_1d(np.squeeze(x))
                            ) for x in args]
    except:
        raise ValueError(not_1d_err_msg)

    try:
        dimension_list = [x.ndim for x in regular_args]
    except AttributeError:
        raise ValueError(not_1d_err_msg)

    # do we have 2d elements?
    if max(dimension_list) > 1:
        raise ValueError(not_1d_err_msg)

    degree_list = np.array([x.size - 1 for x in regular_args])
    max_degree = np.max(degree_list)
    max_degree_index = np.argmax(degree_list)

    try:
        # There are polynomials of lesser degree
        second_max_degree = np.max(degree_list[degree_list < max_degree])
    except ValueError:
        # all degrees are the same
        second_max_degree = max_degree

    n, p, h = max_degree, second_max_degree, len(regular_args) - 1

    # If a single item is passed then return it back
    if h == 0:
        return regular_args[0]

    if n == 0:
        return np.array([1])

    if n > 0 and p == 0:
        return regular_args.pop(max_degree_index)

    # pop out the max degree polynomial and zero pad
    # such that we have n+m columns
    S = np.array([np.hstack((
            regular_args.pop(max_degree_index),
            np.zeros((1, p-1)).squeeze()
            ))]*p)

    # Shift rows to the left
    for rows in range(S.shape[0]):
        S[rows] = np.roll(S[rows], rows)

    # do the same to the remaining ones inside the regular_args
    for item in regular_args:
        _ = np.array([np.hstack((item, [0]*(n+p-item.size)))]*(
                      n+p-item.size+1))
        for rows in range(_.shape[0]):
            _[rows] = np.roll(_[rows], rows)
        S = np.r_[S, _]

    rank_of_sylmat = np.linalg.matrix_rank(S)

    if rank_of_sylmat == min(S.shape):
        return np.array([1])
    else:
        p, l, u = lu(S)

    u[abs(u) < 1e-8] = 0
    for rows in range(u.shape[0]-1, 0, -1):
        if not any(u[rows, :]):
            u = np.delete(u, rows, 0)
        else:
            break

    gcdpoly = np.real(haroldtrimleftzeros(u[-1, :]))
    # make it monic
    gcdpoly /= gcdpoly[0]

    return gcdpoly


def haroldcompanion(somearray):
    """
    Takes a 1D numpy array or list and returns the companion matrix
    of the monic polynomial of somearray. Hence ``[0.5,1,2]`` will be first
    converted to ``[1,2,4]``.

    Example: ::

        >>>> haroldcompanion([2,4,6])
            array([[ 0.,  1.],
                   [-3., -2.]])

        >>>> haroldcompanion([1,3])
            array([[-3.]])

        >>>> haroldcompanion([1])
            array([], dtype=float64)

    """
    if not isinstance(somearray, (list, type(np.array([0.])))):
        raise TypeError('Companion matrices are meant only for '
                        '1D lists or 1D Numpy arrays. I found '
                        'a \"{0}\"'.format(type(somearray).__name__))

    if len(somearray) == 0:
        return np.array([])

    # regularize to flat 1D np.array
    somearray = np.array(somearray, dtype='float').flatten()

    ta = haroldtrimleftzeros(somearray)
    # convert to monic polynomial.
    # Note: ta *=... syntax doesn't autoconvert to float
    ta = np.array(1/ta[0])*ta
    ta = -ta[-1:0:-1]
    n = ta.size

    if n == 0:  # Constant polynomial
        return np.array([])

    elif n == 1:  # First-order --> companion matrix is a scalar
        return np.atleast_2d(np.array(ta))

    else:  # Other stuff
        return np.vstack((np.hstack((np.zeros((n-1, 1)), np.eye(n-1))), ta))


def haroldtrimleftzeros(somearray):
    """
    Trims the insignificant zeros in an array on the left hand side, e.g.,
    ``[0,0,2,3,1,0]`` becomes ``[2,3,1,0]``.

    Parameters
    ----------

    somearray : 1D Numpy array

    Returns
    -------

    anotherarray : 1D Numpy array

    """

    # We trim the leftmost zero entries modeling the absent high-order terms
    # in an array, i.e., [0,0,2,3,1,0] becomes [2,3,1,0]

    arg = np.atleast_2d(somearray).flatten()

    if arg.ndim > 1:
        raise ValueError('The argument is not 1D array-like hence cannot be'
                         ' trimmed unambiguously.')

    if np.count_nonzero(arg) != 0:  # if not all zero
        try:
            n = next(x for x, y in enumerate(arg) if y != 0.)
            return np.array(arg)[n::]
        except StopIteration:
            return np.array(arg[::])
    else:
        return np.array([0.])


def haroldpoly(rootlist):
    """
    Takes a 1D array-like numerical elements as roots and forms the polynomial
    """
    if isinstance(rootlist, collections.Iterable):
        r = np.array([x for x in rootlist], dtype=complex)
    else:
        raise TypeError('The argument must be something iterable,\nsuch as '
                        'list, numpy array, tuple etc. I don\'t know\nwhat '
                        'to do with a \"{0}\" object.'
                        ''.format(type(rootlist).__name__))

    n = r.size
    if n == 0:
        return np.ones(1)
    else:
        p = np.array([0.+0j for x in range(n+1)], dtype=complex)
        p[0] = 1  # Monic polynomial
        p[1] = -rootlist[0]
        for x in range(1, n):
            p[x+1] = -p[x]*r[x]
            for y in range(x, 0, -1):
                p[y] -= p[y-1] * r[x]
        return p


def haroldpolyadd(*args, trimzeros=True):
    """
    Similar to official polyadd from numpy but allows for
    multiple args and doesn't invert the order,
    """
    if trimzeros:
        trimmedargs = tuple(map(haroldtrimleftzeros, args))
    else:
        trimmedargs = args

    degs = [len(m) for m in trimmedargs]  # Get the max len of args
    s = np.zeros((1, max(degs)))
    for ind, x in enumerate(trimmedargs):
        s[0, max(degs)-degs[ind]:] += np.real(x)
    return s[0]


def haroldpolymul(*args, trimzeros=True):
    """
    Simple wrapper around the scipy convolve function
    for polynomial multiplication with multiple args.
    The arguments are passed through the left zero
    trimming function first.

    Example: ::

        >>>> haroldpolymul([0,2,0],[0,0,0,1,3,3,1],[0,0.5,0.5])
        array([ 1.,  4.,  6.,  4.,  1.,  0.])


    """
    # TODO: Make sure we have 1D arrays for convolution
    # numpy convolve is too picky.

    if trimzeros:
        trimmedargs = tuple(map(haroldtrimleftzeros, args))
    else:
        trimmedargs = args

    p = trimmedargs[0]

    for x in trimmedargs[1:]:
        try:
            p = np.convolve(p, x)
        except ValueError:
            p = np.convolve(p.flatten(), x.flatten())

    return p


def haroldpolydiv(dividend, divisor):
    """
    Polynomial division wrapped around scipy deconvolve
    function. Takes two arguments and divides the first
    by the second.

    Returns, two arguments: the factor and the remainder,
    both passed through a left zeros trimming function.
    """
    h_factor, h_remainder = map(haroldtrimleftzeros,
                                deconvolve(dividend, divisor)
                                )

    return h_factor, h_remainder
