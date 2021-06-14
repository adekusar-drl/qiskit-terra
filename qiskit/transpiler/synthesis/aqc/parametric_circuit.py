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

"""
This is the Parametric Circuit class: anything that you need for a circuit
to be parametrized and used for approximate compiling optimization.
"""

# Avoid excessive deprecation warnings in Qiskit on Linux system.
from typing import Optional

import numpy as np
from numpy import linalg as la

from qiskit import QuantumCircuit
from .cnot_structures import make_cnot_network
from .elementary_operations import op_rx, op_ry, op_rz, op_unitary, op_cnot
from .fast_gradient.fast_gradient import FastGradient
from .gradient import GradientBase, DefaultGradient

# TODO: remove gradient parameter in constructor!
# TODO: describe kwargs "layout", "connectivity", "depth" in constructor.
# TODO: make ParametricCircuit more abstract and independent of the CNOT unit that we choose
# TODO: actually computes V from thetas for the specific cnot structure,
#  same computation are done in the gradient implementations - badness
# TODO: document kwargs in constructor.

# TODO: do we need kwargs???
# Individual parameters passed in kwargs of ParametricCircuit and their combination.
# The definitions help to identify misspelled parameter.
PARAM_LAYOUT = "layout"
PARAM_CONNECTIVITY = "connectivity"
PARAM_DEPTH = "depth"
ALL_PARAMS = {PARAM_LAYOUT, PARAM_CONNECTIVITY, PARAM_DEPTH}


class ParametricCircuit:

    """A class that represents an approximating circuit."""

    def __init__(
        self,
        num_qubits: int,
        cnots: Optional[np.ndarray] = None,
        thetas: Optional[np.ndarray] = None,
        gradient: Optional[GradientBase] = None,
        **kwargs,
    ) -> None:
        """
        Args:
            num_qubits: the number of qubits.
            cnots: is an array of dimensions 2 x L indicating where the
                   CNOT units will be placed.
            thetas: vector of circuit parameters.
            gradient: object that computes gradient and objective function.
            kwargs: other parameters.

        Raises:
            ValueError: if an unsupported parameter is passed.
        """

        assert isinstance(num_qubits, int) and num_qubits >= 1
        assert (gradient is None) or isinstance(gradient, GradientBase)

        # If CNOT structure was not specified explicitly, it must be defined
        # in the few properties in "kwargs" or chosen by default.
        if cnots is None:
            for key in kwargs:
                if key not in ALL_PARAMS:
                    raise ValueError(f"Misspelled parameter {key}")

            cnots = make_cnot_network(
                num_qubits=num_qubits,
                network_layout=kwargs.get(PARAM_LAYOUT, "spin"),
                connectivity_type=kwargs.get(PARAM_CONNECTIVITY, "full"),
                depth=kwargs.get(PARAM_DEPTH, int(0)),
            )
        assert isinstance(cnots, np.ndarray)
        assert cnots.size > 0 and cnots.shape == (2, cnots.size // 2)
        assert cnots.dtype == np.int64 or cnots.dtype == int

        self._num_qubits = num_qubits
        self._cnots = cnots.copy()
        self._num_cnots = cnots.shape[1]
        self._thetas = np.full(self.num_thetas, fill_value=0, dtype=np.float64)
        self._gradient = gradient

        if thetas is not None:
            self.set_thetas(thetas)

    @property
    def num_qubits(self) -> int:
        """
        Returns:
            Number of qubits this circuit supports.
        """
        return self._num_qubits

    @property
    def num_cnots(self) -> int:
        """
        Returns:
            Number of CNOT units in the CNOT structure.
        """
        return self._num_cnots

    @property
    def num_thetas_per_cnot(self) -> int:
        """
        Returns:
            Number of angular parameters per a single CNOT.
        """
        return int(4)

    @property
    def num_angles(self) -> int:
        """
        Returns:
            Number of angles/rotations in this circuit
        """
        return 3 * self._num_qubits + 4 * self._num_cnots

    @property
    def num_thetas(self) -> int:
        """
        Returns:
            Number of parameters (angles) of rotation gates in this circuit.
        """
        return 3 * self._num_qubits + 4 * self._num_cnots

    @property
    def cnots(self) -> np.ndarray:
        """
        Returns:
            A CNOT structure this circuit is built from.
        """
        return self._cnots

    @property
    def thetas(self) -> np.ndarray:
        """
        Returns vector of parameters of this circuit.
        Returns:
            Parameters of rotation gates in this circuit.
        """
        return self._thetas

    def set_thetas(self, thetas: np.ndarray):
        """
        Updates theta parameters by the new values.

        Args:
            thetas: new parameters.

        Raises:
            ValueError: if new thetas are not the same size as previous ones.
        """
        assert isinstance(thetas, np.ndarray) and thetas.dtype == np.float64
        if thetas.size != self.num_thetas:
            raise ValueError("wrong size of array of theta parameters")
        np.copyto(self._thetas, thetas.ravel())

    def set_nonzero_thetas(self, thetas: np.ndarray, nonzero_mask: np.ndarray):
        """
        Updates those theta parameters that can take arbitrary values.

        Args:
            thetas: new parameters; this vector is generally shorter than
                    the internal one and contains only those parameters
                    that can take arbitrary values.
            nonzero_mask: boolean mask where True corresponds to a parameter
                          with an arbitrary value, and False corresponds to
                          a parameter with exactly zero value.

        Raises:
            ValueError: if incorrect parameters are passed.
        """
        assert isinstance(thetas, np.ndarray) and thetas.dtype == np.float64
        assert isinstance(nonzero_mask, np.ndarray) and nonzero_mask.dtype == bool
        if nonzero_mask.size != self.num_thetas:
            raise ValueError("wrong size of a mask of nonzero theta parameters")
        if np.count_nonzero(nonzero_mask) != thetas.size:
            raise ValueError("mismatch between the mask and the vector of thetas")
        self._thetas.fill(0.0)
        self._thetas[nonzero_mask.ravel()] = thetas.ravel()

    def init_gradient_backend(self, backend: str):
        """
        Instantiates the gradient backend object. Rationale: gradient object
        can be very large, if some sort of caching is being used internally.
        As such, transforming a circuit (e.g. by compression) can be expensive,
        if we need to reinitialize the gradient object after any circuit
        transformation. Instead, we use this function to choose desired gradient
        backend right before running an actual optimization.

        Args:
            backend: name of gradient backend.

        Raises:
            ValueError: when an unsupported backed is passed.
        """
        assert isinstance(backend, str)
        if self._gradient:
            del self._gradient  # dispose existing backend, if any
            self._gradient = None
        if backend == "default":
            self._gradient = DefaultGradient(self._num_qubits, self._cnots)
        elif backend == "fast":
            self._gradient = FastGradient(self._num_qubits, self._cnots)
        else:
            raise ValueError(f"Unsupported gradient backend {backend}")

    # def get_gradient(self, thetas: (np.ndarray, None),
    #                  target_matrix: np.ndarray) -> (float, np.ndarray):
    #     """
    #     Computes gradient and objective function given the current
    #     circuit parameters. N O T E, if the argument 'thetas' is not None,
    #     then the new thetas will overwrite parameters of this circuit before
    #     gradient computation, beware.
    #     Args:
    #         thetas: if None, then the gradient will be evaluated on the current
    #                 parameters, otherwise the parameters will be updated by
    #                 these new thetas before the gradient computation.
    #         target_matrix: the matrix we are going to approximate.
    #     Returns:
    #         objective function value, gradient.
    #     """
    #     if self._gradient is None:
    #         raise RuntimeError("Gradient backend has not been instantiated")
    #     if thetas is not None:
    #         self.set_thetas(thetas)
    #     return self._gradient.get_gradient(self._thetas, target_matrix)

    def get_gradient(self, target_matrix: np.ndarray) -> (float, np.ndarray):
        """
        Computes gradient and objective function given the current
        circuit parameters.

        Args:
            target_matrix: the matrix we are going to approximate.

        Returns:
            objective function value, gradient.

        Raises:
            RuntimeError: if gradient backend is not instantiated.
        """
        if self._gradient is None:
            raise RuntimeError("Gradient backend has not been instantiated")
        return self._gradient.get_gradient(self._thetas, target_matrix)

    def to_numpy(self) -> np.ndarray:
        """
        Circuit builds a matrix representation of this parametric circuit.
        Returns:
            2^n x 2^n numpy matrix corresponding to this circuit.
        """
        n = self._num_qubits
        L = self._num_cnots
        thetas = self._thetas
        cnots = self._cnots

        V = np.eye(2 ** n)
        for l in range(L):
            p = 4 * l
            a = op_ry(thetas[0 + p])
            b = op_rz(thetas[1 + p])
            c = op_ry(thetas[2 + p])
            d = op_rx(thetas[3 + p])
            # Extract where the CNOT goes
            q1 = int(cnots[0, l])
            q2 = int(cnots[1, l])
            u1 = np.dot(b, a)
            u2 = np.dot(d, c)
            U1 = op_unitary(u1, n, q1)
            U2 = op_unitary(u2, n, q2)
            CNOT1 = op_cnot(n, q1, q2)
            # Build the CNOT unit, our basic structure
            C = la.multi_dot([U2, U1, CNOT1])
            # Concatenate the CNOT unit
            V = np.dot(C, V)

        # Add the first rotation gates: ZYZ
        V1 = 1
        for k in range(n):
            p = 4 * L + 3 * k
            a = op_rz(thetas[0 + p])
            b = op_ry(thetas[1 + p])
            c = op_rz(thetas[2 + p])
            V1 = np.kron(V1, la.multi_dot([a, b, c]))
        V = np.dot(V, V1)
        return V

    def to_qiskit(self, tol: float = 0.0, reverse: bool = False) -> QuantumCircuit:
        """
        Makes a Qiskit quantum circuit from this parametric one.
        N O T E, reverse=False is a bit misleading default value. By setting it
        to False, we actually reverse the bit order to comply with Qiskit bit
        ordering convention, which is opposite to conventional one. Keep it
        always equal False, unless the tensor product ordering is changed in
        gradient computation.

        Args:
            tol: angle parameter less or equal this (small) value is considered
                 equal zero and corresponding gate is not inserted into the
                 output circuit (because it becomes identity one in this case).
            reverse: recommended False value.

        Returns:
            A quantum circuit converted from this parametric circuit.
        """
        n = self._num_qubits
        L = self._num_cnots
        thetas = self._thetas
        cnots = self._cnots
        qc = QuantumCircuit(n, 1)

        for k in range(n):
            p = 4 * L + 3 * k
            # TODO: revise the code
            # if reverse:
            #     k = k   # pylint: disable=self-assigning-variable
            if not reverse:
                k = n - k - 1
            if np.abs(thetas[2 + p]) > tol:
                qc.rz(thetas[2 + p], k)
            if np.abs(thetas[1 + p]) > tol:
                qc.ry(thetas[1 + p], k)
            if np.abs(thetas[0 + p]) > tol:
                qc.rz(thetas[0 + p], k)

        for c in range(L):
            p = 4 * c
            # Extract where the CNOT goes
            q1 = int(cnots[0, c]) - 1  # 1-based index
            q2 = int(cnots[1, c]) - 1  # 1-based index
            # TODO: revise the code
            # if reverse:
            #     q1 = q1
            #     q2 = q2
            if not reverse:
                q1 = n - q1 - 1
                q2 = n - q2 - 1
            qc.cx(q1, q2)
            if np.abs(thetas[0 + p]) > tol:
                qc.ry(thetas[0 + p], q1)
            if np.abs(thetas[1 + p]) > tol:
                qc.rz(thetas[1 + p], q1)
            if np.abs(thetas[2 + p]) > tol:
                qc.ry(thetas[2 + p], q2)
            if np.abs(thetas[3 + p]) > tol:
                qc.rx(thetas[3 + p], q2)

        return qc
