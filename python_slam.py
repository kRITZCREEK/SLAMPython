# coding=utf-8
# FastSLAM.
# Particle member function 'update_particle()' is implemented which is
# (among some other helper functions) the final step for a fully functional
# SLAM correction step.
#
from lego_robot import *
from slam_g_library import get_cylinders_from_scan, write_cylinders,\
     write_error_ellipses, get_mean, get_error_ellipse_and_heading_variance,\
     print_particles
from math import sin, cos, pi, atan2, sqrt, exp
import copy
import random
import numpy as np


class Particle:
    def __init__(self, pose):
        self.pose = pose
        self.landmark_positions = []
        self.landmark_covariances = []

    def number_of_landmarks(self):
        """Utility: return current number of landmarks in this particle."""
        return len(self.landmark_positions)

    @staticmethod
    def g(state, control, w):
        """State transition. This is exactly the same method as in the Kalman
           filter."""
        x, y, theta = state
        l, r = control
        if r != l:
            alpha = (r - l) / w
            rad = l/alpha
            g1 = x + (rad + w/2.)*(sin(theta+alpha) - sin(theta))
            g2 = y + (rad + w/2.)*(-cos(theta+alpha) + cos(theta))
            g3 = (theta + alpha + pi) % (2*pi) - pi
        else:
            g1 = x + l * cos(theta)
            g2 = y + l * sin(theta)
            g3 = theta
        return np.array([g1, g2, g3])

    def move(self, left, right, w):
        """Given left, right control and robot width, move the robot."""
        self.pose = self.g(self.pose, (left, right), w)

    @staticmethod
    def h(state, landmark, scanner_displacement):
        """Measurement function. Takes a (x, y, theta) state and a (x, y)
           landmark, and returns the corresponding (range, bearing)."""
        dx = landmark[0] - (state[0] + scanner_displacement * cos(state[2]))
        dy = landmark[1] - (state[1] + scanner_displacement * sin(state[2]))
        r = sqrt(dx * dx + dy * dy)
        alpha = (atan2(dy, dx) - state[2] + pi) % (2*pi) - pi
        return np.array([r, alpha])

    @staticmethod
    def dh_dlandmark(state, landmark, scanner_displacement):
        """Derivative with respect to the landmark coordinates. This is related
           to the dh_dstate function we used earlier (it is:
           -dh_dstate[0:2,0:2])."""
        theta = state[2]
        cost, sint = cos(theta), sin(theta)
        dx = landmark[0] - (state[0] + scanner_displacement * cost)
        dy = landmark[1] - (state[1] + scanner_displacement * sint)
        q = dx * dx + dy * dy
        sqrtq = sqrt(q)
        dr_dmx = dx / sqrtq
        dr_dmy = dy / sqrtq
        dalpha_dmx = -dy / q
        dalpha_dmy =  dx / q

        return np.array([[dr_dmx, dr_dmy],
                         [dalpha_dmx, dalpha_dmy]])

    def h_expected_measurement_for_landmark(self, landmark_number,
                                            scanner_displacement):
        """Returns the expected distance and bearing measurement for a given
           landmark number and the pose of this particle."""
        return self.h(self.pose, self.landmark_positions[landmark_number], scanner_displacement)

    def H_Ql_jacobian_and_measurement_covariance_for_landmark(
        self, landmark_number, Qt_measurement_covariance, scanner_displacement):
        """Computes Jacobian H of measurement function at the particle's
           position and the landmark given by landmark_number. Also computes the
           measurement covariance matrix."""
        # - H is computed using dh_dlandmark.
        H = self.dh_dlandmark(self.pose, self.landmark_positions[landmark_number], scanner_displacement)
        # - To compute Ql, you will need the product of two matrices,
        #   which is np.dot(A, B).
        Ql = np.dot(H, np.dot(self.landmark_covariances[landmark_number], H.T)) + Qt_measurement_covariance
        return (H, Ql)

    def wl_likelihood_of_correspondence(self, measurement,
                                        landmark_number,
                                        Qt_measurement_covariance,
                                        scanner_displacement):
        """For a given measurement and landmark_number, returns the likelihood
           that the measurement corresponds to the landmark."""
        # --->>> Insert your code here.
        # Hints:
        # - You will need delta_z, which is the measurement minus the
        #   expected_measurement_for_landmark()
        delta_z = measurement - self.h_expected_measurement_for_landmark(landmark_number, scanner_displacement)
        H, Ql = self.H_Ql_jacobian_and_measurement_covariance_for_landmark(landmark_number, Qt_measurement_covariance,
                                                                        scanner_displacement)

        # - Ql is obtained using a call to
        #   H_Ql_jacobian_and_measurement_covariance_for_landmark(). You
        #   will only need Ql, not H
        # - np.linalg.det(A) computes the determinant of A
        # - np.dot() does not distinguish between row and column vectors.

        return 1.0 / (2*pi * sqrt(np.linalg.det(Ql))) * exp(np.dot(np.dot(-0.5 * delta_z.T, np.linalg.inv(Ql)), delta_z))

    def compute_correspondence_likelihoods(self, measurement,
                                           number_of_landmarks,
                                           Qt_measurement_covariance,
                                           scanner_displacement):
        """For a given measurement, returns a list of all correspondence
           likelihoods (from index 0 to number_of_landmarks-1)."""
        likelihoods = []
        for i in xrange(number_of_landmarks):
            likelihoods.append(
                self.wl_likelihood_of_correspondence(
                    measurement, i, Qt_measurement_covariance,
                    scanner_displacement))
        return likelihoods

    def initialize_new_landmark(self, measurement_in_scanner_system,
                                Qt_measurement_covariance,
                                scanner_displacement):
        """Given a (x, y) measurement in the scanner's system, initializes a
           new landmark and its covariance."""
        scanner_pose = (self.pose[0] + cos(self.pose[2]) * scanner_displacement,
                        self.pose[1] + sin(self.pose[2]) * scanner_displacement,
                        self.pose[2])
        # --->>> Insert your code here.
        # Hints:
        # - LegoLogfile.scanner_to_world() (from lego_robot.py) will return
        #   the world coordinate, given the scanner pose and the coordinate in
        #   the scanner's system.

        landmark_position = LegoLogfile.scanner_to_world(scanner_pose, measurement_in_scanner_system)

        # - H is obtained from dh_dlandmark()
        H = self.dh_dlandmark(self.pose, landmark_position, scanner_displacement)
        H_inv = np.linalg.inv(H)
        # - Use np.linalg.inv(A) to invert matrix A
        # - As usual, np.dot(A,B) is the matrix product of A and B.
        landmark_covariance = np.dot(np.dot(H_inv, Qt_measurement_covariance), H_inv.T)

        self.landmark_positions.append(landmark_position)  # Replace this.
        self.landmark_covariances.append(landmark_covariance)  # Replace this.

    def update_landmark(self, landmark_number, measurement,
                        Qt_measurement_covariance, scanner_displacement):
        """Update a landmark's estimated position and covariance."""

        # Hints:
        # - H and Ql can be computed using
        #   H_Ql_jacobian_and_measurement_covariance_for_landmark()
        H, Ql = self.H_Ql_jacobian_and_measurement_covariance_for_landmark(landmark_number, Qt_measurement_covariance,
                                                                           scanner_displacement)

        K = np.dot(np.dot(self.landmark_covariances[landmark_number], H.T), np.linalg.inv(Ql))

        self.landmark_positions[landmark_number] = self.landmark_positions[landmark_number] +\
                 np.dot(K, measurement - self.h_expected_measurement_for_landmark(landmark_number,scanner_displacement ))

        self.landmark_covariances[landmark_number] = np.dot(np.eye(2) - np.dot(K, H),
                                                            self.landmark_covariances[landmark_number])

    def update_particle(self, measurement, measurement_in_scanner_system,
                        number_of_landmarks,
                        minimum_correspondence_likelihood,
                        Qt_measurement_covariance, scanner_displacement):
        """Given a measurement, computes the likelihood that it belongs to any
           of the landmarks in the particle. If there are none, or if all
           likelihoods are below the minimum_correspondence_likelihood
           threshold, add a landmark to the particle. Otherwise, update the
           (existing) landmark with the largest likelihood."""
        # --->>> Insert your code below, at the marked locations.
        
        # Compute likelihood of correspondence of measurement to all landmarks
        # (from 0 to number_of_landmarks-1).
        likelihoods = self.compute_correspondence_likelihoods(measurement, number_of_landmarks,
                                                              Qt_measurement_covariance, scanner_displacement)
        # If the likelihood list is empty, or the max correspondence likelihood
        # is still smaller than minimum_correspondence_likelihood, setup
        # a new landmark.
        if not likelihoods or\
           max(likelihoods) < minimum_correspondence_likelihood:
            self.initialize_new_landmark(measurement_in_scanner_system, Qt_measurement_covariance, scanner_displacement)
            return minimum_correspondence_likelihood

        # Else update the particle's EKF for the corresponding particle.
        else:
            # This computes (max, argmax) of measurement_likelihoods.
            w = 0
            max_index = 0
            for index, likelihood in enumerate(likelihoods):
              if likelihood > w:
                w = likelihood
                max_index = index

            # Add code to update_landmark().
            self.update_landmark(max_index, measurement, Qt_measurement_covariance, scanner_displacement)
            return w

class FastSLAM:
    def __init__(self, initial_particles,
                 robot_width, scanner_displacement,
                 control_motion_factor, control_turn_factor,
                 measurement_distance_stddev, measurement_angle_stddev,
                 minimum_correspondence_likelihood):
        # The particles.
        self.particles = initial_particles

        # Some constants.
        self.robot_width = robot_width
        self.scanner_displacement = scanner_displacement
        self.control_motion_factor = control_motion_factor
        self.control_turn_factor = control_turn_factor
        self.measurement_distance_stddev = measurement_distance_stddev
        self.measurement_angle_stddev = measurement_angle_stddev
        self.minimum_correspondence_likelihood = \
            minimum_correspondence_likelihood

    def predict(self, control):
        """The prediction step of the particle filter."""
        left, right = control
        left_std  = sqrt((self.control_motion_factor * left)**2 +\
                        (self.control_turn_factor * (left-right))**2)
        right_std = sqrt((self.control_motion_factor * right)**2 +\
                         (self.control_turn_factor * (left-right))**2)
        # Modify list of particles: for each particle, predict its new position.
        for p in self.particles:
            l = random.gauss(left, left_std)
            r = random.gauss(right, right_std)
            p.move(l, r, self.robot_width)

    def update_and_compute_weights(self, cylinders):
        """Updates all particles and returns a list of their weights."""
        Qt_measurement_covariance = \
            np.diag([self.measurement_distance_stddev**2,
                     self.measurement_angle_stddev**2])
        weights = []
        for p in self.particles:
            # Loop over all measurements.
            number_of_landmarks = p.number_of_landmarks()
            weight = 1.0
            #   measurement := (Winkel, Abstand)
            #   measurement_in_scanner_system := (x, y) im Scanner System
            for measurement, measurement_in_scanner_system in cylinders:
                weight *= p.update_particle(
                    measurement, measurement_in_scanner_system,
                    number_of_landmarks,
                    self.minimum_correspondence_likelihood,
                    Qt_measurement_covariance, scanner_displacement)

            # Append overall weight of this particle to weight list.
            weights.append(weight)

        return weights

    def resample(self, weights):
        """Return a list of particles which have been resampled, proportional
           to the given weights."""
        new_particles = []
        max_weight = max(weights)
        index = random.randint(0, len(self.particles) - 1)
        offset = 0.0
        for i in xrange(len(self.particles)):
            offset += random.uniform(0, 2.0 * max_weight)
            while offset > weights[index]:
                offset -= weights[index]
                index = (index + 1) % len(weights)
            new_particles.append(copy.deepcopy(self.particles[index]))
        return new_particles

    def correct(self, cylinders):
        """The correction step of FastSLAM."""
        # Update all particles and compute their weights.
        weights = self.update_and_compute_weights(cylinders)
        # Then resample, based on the weight array.
        # TODO: Genau derselbe resampling Algorithmus wie auch bei evolutionaeren Algo verwendet
        self.particles = self.resample(weights)


if __name__ == '__main__':
    # Robot constants.
    scanner_displacement = 3.0 # Wie weit ist der Scanner entgegen der Radachse verschoben?
    #TODO: Muss nochmal kalibriert werden. 28.01
    ticks_to_mm = 0.500 # Motor Ticks zu mm
    robot_width = 120.0

    # Cylinder extraction and matching constants.
    minimum_valid_distance = 20.0 # Nur Messwerte über 20mm werden akzeptiert
    depth_jump = 80.0 # Ein Feature wird ab einem Sprung von 100mm Distanz angenommen
    cylinder_offset = 90.0 # Radius des Zylinders

    # Filter constants.
    control_motion_factor = 0.15  # Error in motor control.
    control_turn_factor = 0.2  # Additional error due to slip when turning.
    measurement_distance_stddev = 100.0  # Distance measurement error of cylinders.
    measurement_angle_stddev = 45.0 / 180.0 * pi  # Angle measurement error.
    # TODO: muss wahrscheinlich kleiner eingestellt werden
    minimum_correspondence_likelihood = 0.0001  # Min likelihood of correspondence.

    # Generate initial particles. Each particle is (x, y, theta).
    number_of_particles = 200
    # TODO: Muss an die tatsächliche Größe der Arena angepasst werden
    start_state = np.array([1000.0, 1000.0, 45.0 / 180.0 * pi])
    initial_particles = [copy.copy(Particle(start_state))
                         for _ in xrange(number_of_particles)]

    # Setup filter.
    fs = FastSLAM(initial_particles,
                  robot_width, scanner_displacement,
                  control_motion_factor, control_turn_factor,
                  measurement_distance_stddev,
                  measurement_angle_stddev,
                  minimum_correspondence_likelihood)

    # Read data.
    logfile = LegoLogfile()
    logfile.read("motor_log.txt")
    logfile.read("uss_log.txt")

    # Loop over all motor tick records.
    # This is the FastSLAM filter loop, with prediction and correction.
    f = open("fast_slam_correction.txt", "w")
    for i in xrange(len(logfile.motor_ticks)):
        # Prediction.
        control = map(lambda x: x * ticks_to_mm, logfile.motor_ticks[i])
        fs.predict(control)

        # Correction.
        cylinders = get_cylinders_from_scan(logfile.scan_data[i], depth_jump,
            minimum_valid_distance, cylinder_offset)
        fs.correct(cylinders)

        # Output particles.
        print_particles(fs.particles, f)

        # Output state estimated from all particles.
        mean = get_mean(fs.particles)
        print >> f, "F %.0f %.0f %.3f" %\
              (mean[0] + scanner_displacement * cos(mean[2]),
               mean[1] + scanner_displacement * sin(mean[2]),
               mean[2])

        # Output error ellipse and standard deviation of heading.
        errors = get_error_ellipse_and_heading_variance(fs.particles, mean)
        print >> f, "E %.3f %.0f %.0f %.3f" % errors

        # Output landmarks of particle which is closest to the mean position.
        output_particle = min([
            (np.linalg.norm(mean[0:2] - fs.particles[i].pose[0:2]),i)
            for i in xrange(len(fs.particles)) ])[1]

        print fs.particles[output_particle].landmark_positions
        # Write estimates of landmarks.
        write_cylinders(f, "W C",
                        fs.particles[output_particle].landmark_positions)
        # Write covariance matrices.
        write_error_ellipses(f, "W E",
                             fs.particles[output_particle].landmark_covariances)

    f.close()
