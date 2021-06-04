# This code is part of Qiskit.
#
# (C) Copyright IBM 2021.
#
# This code is licensed under the Apache License, Version 2.0. You may
# obtain a copy of this license in the LICENSE.txt file in the root directory
# of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
#
# Any modifications or derivative works of this code must retain this
# copyright notice, and modified files need to carry a notice indicating
# that they have been altered from the originals.

import numpy as np
from typing import Union
import inspect
import cmath


def getMaxNumBits() -> int:
    """
    Returns the maximum supported number of qubits handled by this approach.
    Note, 2^16 means that the size of circuit matrix is 2^16 x 2^16 = 2^32,
    which is huge.
    """
    return int(16)


def isNaturalBitOrdering() -> bool:
    """
    Returns True, if so called "natural" bit ordering is adopted.
    I M P O R T A N T:
    The current code relies on "non-natural" bit ordering convention, where
    the state vector is defined as a chain of Kronecker products of individual
    qubit states as follows:
    |state> = |least-significant-qubit> kron ... kron |most-significant-qubit>
    In quantum computation another ("natural") bit ordering is adopted:
    |state> = |most-significant-qubit> kron ... kron |least-significant-qubit>
    Non-natural bit ordering is more linear algebra friendly. However, if we
    consider a "natural" representation of a number:
    |x> = |x1 x2 ... xn> = x1 * 2^{n-1} + x2 * 2^{n-2} + ... + xn * 2^{0}, where
    x1 is a 0/1 value of the most significant bit, xn is a 0/1 value of the
    least significant one, then representation becomes intuitive for enumerating
    the quantum states. For example, |0> = (1 0 ... 0), |1> = (0 1 ... 0),
    |2^n - 1> = (0 0 ... 1). In the case of non-natural settings, in order to
    make a state |k> we have to flip bit ordering in the bit representation
    of the number 'k'. This is the rational for the function ReverseBits().
    I M P O R T A N T:
    At the moment we apply ReverseBits() even in case of natural ordering,
    because we traverse a number starting from the least-significant bit. Had
    it done the other way, the ReverseBits() would be unnecessary. TODO: fix it.
    """
    return False


def isPermutation(x: np.ndarray) -> bool:
    """
    Checks if array is really an index permutation.
    """
    return (
        isinstance(x, np.ndarray)
        and x.ndim == 1
        and x.dtype == np.int64
        and np.all(np.sort(x) == np.arange(x.size, dtype=np.int64))
    )


def ReverseBits(x: (int, np.ndarray), nbits: int, enable: bool) -> Union[int, np.ndarray]:
    """
    Reverses the bit order in a number of 'nbits' length. If 'x' is an array,
    then operation is applied to every entry.
    :param x: either a single integer or an array of integers.
    :param nbits: number of meaningful bits in the number 'x'.
    :param enable: apply reverse operation, if enabled, otherwise leave unchanged.
    :return: a number or array of numbers with reversed bits.
    """
    assert isinstance(nbits, int) and 1 <= nbits <= getMaxNumBits()
    assert isinstance(enable, bool)

    if not enable:
        if isinstance(x, int):
            assert 0 <= x < 2 ** nbits
        else:
            assert isinstance(x, np.ndarray) and x.dtype == np.int64
            assert np.all((0 <= x) & (x < 2 ** nbits))
            x = x.copy()
        return x

    if isinstance(x, int):
        assert 0 <= x < 2 ** nbits
        res = int(0)
    else:
        assert isinstance(x, np.ndarray) and x.dtype == np.int64
        assert np.all((0 <= x) & (x < 2 ** nbits))
        x = x.copy()
        res = np.full_like(x, fill_value=0)

    for _ in range(nbits):
        res <<= 1
        res |= x & 1
        x >>= 1
    return res


def SwapBits(num: int, a: int, b: int):
    """
    Swaps the bits at positions 'a' and 'b' in the number 'num'.
    """
    x = ((num >> a) ^ (num >> b)) & 1
    return num ^ ((x << a) | (x << b))


def BitPermutation1Q(n: int, k: int) -> np.ndarray:
    """
    Constructs index permutation that brings a circuit consisting of a single
    1-qubit gate to "standard form": kron(I(2^n/2), G), as we call it. Here n
    is the number of qubits, G is a 2x2 gate matrix, I(2^n/2) is the identity
    matrix of size (2^n/2)x(2^n/2), and the full size of the circuit matrix is
    (2^n)x(2^n). Circuit matrix in standard form becomes block-diagonal (with
    sub-matrices G on the main diagonal). Multiplication of such a matrix and
    a dense one is much faster than generic dense-dense product. Moreover,
    we do not need to keep the entire circuit matrix in memory but just 2x2 G
    one. This saves a lot of memory when the number of qubits is large.
    :param n: number of qubits.
    :param k: index of qubit where single 1-qubit gate is applied.
    :return: permutation that brings the whole layer to the standard form.
    """
    assert isinstance(n, int) and isinstance(k, int)
    assert 0 <= k < n <= getMaxNumBits()
    perm = np.arange(2 ** n, dtype=np.int64)
    if k != n - 1:
        for v in range(2 ** n):
            perm[v] = SwapBits(v, k, n - 1)
    return perm


def BitPermutation2Q(n: int, j: int, k: int) -> np.ndarray:
    """
    Constructs index permutation that brings a circuit consisting of a single
    2-qubit gate to "standard form": kron(I(2^n/4), G), as we call it. Here n
    is the number of qubits, G is a 4x4 gate matrix, I(2^n/4) is the identity
    matrix of size (2^n/4)x(2^n/4), and the full size of the circuit matrix is
    (2^n)x(2^n). Circuit matrix in standard form becomes block-diagonal (with
    sub-matrices G on the main diagonal). Multiplication of such a matrix and
    a dense one is much faster than generic dense-dense product. Moreover,
    we do not need to keep the entire circuit matrix in memory but just 4x4 G
    one. This saves a lot of memory when the number of qubits is large.
    :param n: number of qubits.
    :param j: index of control qubit where single 2-qubit gate is applied.
    :param k: index of target qubit where single 2-qubit gate is applied.
    :return: permutation that brings the whole layer to the standard form.
    """
    assert isinstance(n, int) and isinstance(j, int) and isinstance(k, int)
    assert j != k and 0 <= j < n and 0 <= k < n and 2 <= n <= getMaxNumBits()
    N = 2 ** n
    perm = np.arange(N, dtype=np.int64)
    if j < n - 2:
        if k < n - 2:
            for v in range(N):
                perm[v] = SwapBits(SwapBits(v, j, n - 2), k, n - 1)
        elif k == n - 2:
            for v in range(N):
                perm[v] = SwapBits(SwapBits(v, n - 2, n - 1), j, n - 2)
        else:
            assert k == n - 1
            for v in range(N):
                perm[v] = SwapBits(v, j, n - 2)
    elif j == n - 2:
        if k < n - 2:
            for v in range(N):
                perm[v] = SwapBits(v, k, n - 1)
        else:
            assert k == n - 1
    else:
        assert j == n - 1
        if k < n - 2:
            for v in range(N):
                perm[v] = SwapBits(SwapBits(v, n - 2, n - 1), k, n - 1)
        else:
            assert k == n - 2
            for v in range(N):
                perm[v] = SwapBits(v, n - 2, n - 1)
    return perm


def InversePermutation(perm: np.ndarray) -> np.ndarray:
    """
    Returns inverse permutation.
    """
    assert isPermutation(perm)
    inv = np.full_like(perm, fill_value=0)
    inv[perm] = np.arange(perm.size, dtype=np.int64)
    return inv


def Rx(phi: float, out: np.ndarray) -> np.ndarray:
    """
    X-rotation gate. TODO: assertions could be dropped.
    """
    assert isinstance(phi, float) and isinstance(out, np.ndarray)
    assert out.shape == (2, 2) and out.dtype == np.cfloat
    a = 0.5 * phi
    cs, sn = cmath.cos(a), -1j * cmath.sin(a)
    out[0, 0] = cs
    out[0, 1] = sn
    out[1, 0] = sn
    out[1, 1] = cs
    return out


def Ry(phi: float, out: np.ndarray) -> np.ndarray:
    """
    Y-rotation gate. TODO: assertions could be dropped.
    """
    assert isinstance(phi, float) and isinstance(out, np.ndarray)
    assert out.shape == (2, 2) and out.dtype == np.cfloat
    a = 0.5 * phi
    cs, sn = cmath.cos(a), cmath.sin(a)
    out[0, 0] = cs
    out[0, 1] = -sn
    out[1, 0] = sn
    out[1, 1] = cs
    return out


def Rz(phi: float, out: np.ndarray) -> np.ndarray:
    """
    Z-rotation gate. TODO: assertions could be dropped.
    """
    assert isinstance(phi, float) and isinstance(out, np.ndarray)
    assert out.shape == (2, 2) and out.dtype == np.cfloat
    e = cmath.exp(0.5j * phi)
    out[0, 0] = 1 / e
    out[0, 1] = 0
    out[1, 0] = 0
    out[1, 1] = e
    return out


def TemporaryCode(message: (str, None) = None):
    """
    Prints a warning message when temporary code is executed.
    """
    i = inspect.getframeinfo(inspect.currentframe().f_back)
    print("!" * 80)
    print(
        "T E M P O R A R Y code at:\n{:s} : {:s}() : {:d}".format(i.filename, i.function, i.lineno)
    )
    if isinstance(message, str):
        print(message)
    print("!" * 80)
