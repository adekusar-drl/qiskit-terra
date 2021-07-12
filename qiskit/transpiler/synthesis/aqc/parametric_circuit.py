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

from typing import Optional

import numpy as np
from numpy import linalg as la

from qiskit import QuantumCircuit
from .elementary_operations import rx_matrix, ry_matrix, rz_matrix, place_unitary, place_cnot
from .gradient import GradientBase, DefaultGradient

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
        cnots: np.ndarray,
        thetas: Optional[np.ndarray] = None,
        gradient: Optional[GradientBase] = None,
    ) -> None:
        """
        Args:
            num_qubits: the number of qubits.
            cnots: is an array of dimensions ``(2, L)`` indicating where the CNOT units will
                be placed.
            thetas: vector of circuit parameters.
            gradient: object that computes gradient and objective function.

        Raises:
            ValueError: if an unsupported parameter is passed.
        """

        assert isinstance(num_qubits, int) and num_qubits >= 1
        assert (gradient is None) or isinstance(gradient, GradientBase)
        assert isinstance(cnots, np.ndarray)
        assert cnots.size > 0 and cnots.shape == (2, cnots.size // 2)
        assert cnots.dtype == np.int64 or cnots.dtype == int

        self._num_qubits = num_qubits
        self._cnots = cnots
        self._num_cnots = cnots.shape[1]
        if thetas is None:
            thetas = np.random.uniform(0, 2 * np.pi, self.num_thetas)
        self._thetas = thetas
        self._gradient = gradient or DefaultGradient(self._num_qubits, self._cnots)

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
        return 4

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
        self._thetas = thetas

    def get_gradient(self, target_matrix: np.ndarray) -> (float, np.ndarray):
        """
        Computes gradient and objective function given the current circuit parameters.

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

    def to_matrix(self) -> np.ndarray:
        """
        Circuit builds a matrix representation of this parametric circuit.

        Returns:
            A matrix of size ``(2^n, 2^n)`` corresponding to this circuit.
        """

        # this is the matrix corresponding to the cnot unit part of the circuit
        cnot_matrix = np.eye(2 ** self._num_qubits)
        for cnot_index in range(self._num_cnots):
            theta_index = 4 * cnot_index

            # cnot qubit indices for the cnot unit identified by cnot_index
            q1 = int(self._cnots[0, cnot_index])
            q2 = int(self._cnots[1, cnot_index])

            # rotations that are applied on the q1 qubit
            ry1 = ry_matrix(self._thetas[0 + theta_index])
            rz1 = rz_matrix(self._thetas[1 + theta_index])

            # rotations that are applied on the q2 qubit
            ry2 = ry_matrix(self._thetas[2 + theta_index])
            rx2 = rx_matrix(self._thetas[3 + theta_index])

            # combine the rotations on qubits q1 and q2
            single_q1 = np.dot(rz1, ry1)
            single_q2 = np.dot(rx2, ry2)

            # we place single qubit matrices at the corresponding locations in the (2^n, 2^n) matrix
            full_q1 = place_unitary(single_q1, self._num_qubits, q1)
            full_q2 = place_unitary(single_q2, self._num_qubits, q2)

            # we place a cnot matrix at the qubits q1 and q2 in the full matrix
            cnot_q1q2 = place_cnot(self._num_qubits, q1, q2)  # todo: verify the size of cnot1

            # compute the cnot unit matrix
            cnot_unit = la.multi_dot([full_q2, full_q1, cnot_q1q2])

            # Concatenate the CNOT unit
            cnot_matrix = np.dot(cnot_unit, cnot_matrix)

        # this is the matrix corresponding to the initial rotation part of the circuit
        rotation_matrix = 1
        # we start with 1 and kronecker product each qubit's rotations
        for qubit in range(self._num_qubits):
            theta_index = 4 * self._num_cnots + 3 * qubit
            rz0 = rz_matrix(self._thetas[0 + theta_index])
            ry1 = ry_matrix(self._thetas[1 + theta_index])
            rz2 = rz_matrix(self._thetas[2 + theta_index])
            rotation_matrix = np.kron(rotation_matrix, la.multi_dot([rz0, ry1, rz2]))

        # the matrix corresponding to the full circuit is the cnot part and
        # rotation part multiplied together
        circuit_matrix = np.dot(cnot_matrix, rotation_matrix)
        return circuit_matrix

    def to_circuit(self, tol: float = 0.0, reverse: bool = False) -> QuantumCircuit:
        """
        Makes a Qiskit quantum circuit from this parametric one. Note, ``reverse=False`` is a bit
        misleading default value. By setting it to ``False``, we actually reverse the bit order to
        comply with Qiskit bit ordering convention, which is opposite to conventional one. Keep it
        always equal ``False``, unless the tensor product ordering is changed in gradient
        computation.

        Args:
            tol: angle parameter less or equal this (small) value is considered equal zero and
                corresponding gate is not inserted into the output circuit (because it becomes
                identity one in this case).
            reverse: recommended False value.

        Returns:
            A quantum circuit converted from this parametric circuit.
        """
        n = self._num_qubits
        thetas = self._thetas
        cnots = self._cnots
        qc = QuantumCircuit(n, 1)

        for k in range(n):
            p = 4 * self._num_cnots + 3 * k
            if not reverse:
                k = n - k - 1
            if np.abs(thetas[2 + p]) > tol:
                qc.rz(thetas[2 + p], k)
            if np.abs(thetas[1 + p]) > tol:
                qc.ry(thetas[1 + p], k)
            if np.abs(thetas[0 + p]) > tol:
                qc.rz(thetas[0 + p], k)

        for c in range(self._num_cnots):
            p = 4 * c
            # Extract where the CNOT goes
            q1 = int(cnots[0, c]) - 1  # 1-based index
            q2 = int(cnots[1, c]) - 1  # 1-based index
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
