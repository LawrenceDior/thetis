# Geostrophic freshwater cylinder test case
# =========================================
#
# For detailed description and discussion of the test case see
# [1] Tartinville et al. (1998). A coastal ocean model intercomparison study
#     for a three-dimensional idealised test case. Applied Mathematical
#     Modelling, 22(3):165-182.
#     http://dx.doi.org/10.1016/S0307-904X(98)00015-8
#
# Test case setup:
# domain: 30 km x 30 km, 20 m deep
# mesh resolution: 1 km, 20 vertical levels
# coriolis: f=1.15e-4 1/s
# initial salinity: cylinder
#    center: center of domain
#    radius: 3 km
#    depth: surface to 10 m deep
#    salinity inside: 1.1*(r/1000/3)^8 + 33.75 psu
#       (r radial distance in m)
#    salinity outside: 34.85 psu
# equation of state: 1025 + 0.78*(S - 33.75)
# density inside: rho = 1025 + 0.78*1.1*(r/1000/3)^8
# density outside: 1025 + 0.78*1.1 = 1025.858
# initial elevation: zero
# initial velocity: zero
# inertial period: 144 h / 9.5 = 54568.42 s ~= 30 exports
# simulation period: 144 h
#
# S contours are 33.8, 34.0, 34.2, 34.4, 34.6, 34.8
# which correspond to rho' 0.039,  0.195,  0.351,  0.507,  0.663,  0.819
#
# NOTE with SLIM mode-2 instability starts to develop around t=100 h
#
# Tuomas Karna 2015-05-30

from thetis import *


class VorticityCalculator(DiagnosticCallback):
    """
    Computes the total vorticity of the horizontal velocity field.

    Relative vorticity is defined as

    zeta = -dudy + dvdx

    Absolute vorticity is

    q = zeta + f,

    where f is the Coriolis factor.

    This routine computes integral of zeta over the whole domain. Assuming that f
    is a constant, the integral of zeta should be conserved.

    NOTE in this test case zeta is initially zero, so we are not computing relative change.

    """
    name = 'vorticity'
    variable_names = ['vorticity', 'rel_change']

    def _initialize(self):
        self.initial_val = None
        self._initialized = True
        uv = self.solver_obj.fields.uv_3d
        # zeta = du/dy + dv/dy + f
        self.vort_expression = -Dx(uv[0], 1) + Dx(uv[1], 0)
        cylinder_r = 15e3
        cylinder_vol = np.pi*cylinder_r**2*depth
        self.constant_val = f0*cylinder_vol

    def __call__(self):
        if not hasattr(self, '_initialized') or self._initialized is False:
            self._initialize()
        zeta = assemble(self.vort_expression*dx) + self.constant_val
        if self.initial_val is None:
            self.initial_val = zeta
        rel_change = (zeta - self.initial_val)/self.initial_val
        return (zeta, rel_change)

    def message_str(self, *args):
        line = 'vorticity: {:16.10e}, rel. change {:14.8e}'.format(args[0], args[1])
        return line


class AngularMomentumCalculator(DiagnosticCallback):
    """
    Computes the total angular momentum the horizontal velocity field.

    H = \rho (r x u)

    where \rho is the water density, r radial vector from origin, and u the
    horizontal velocity.

    Here we are computing the total momentum as

    q = int_V H dx / int_V \rho dx

    where V is the 3d domain.
    """
    name = 'angmom'
    variable_names = ['angmom']

    def _initialize(self):
        self.initial_val = None
        self._initialized = True
        uv = self.solver_obj.fields.uv_3d
        rho = self.solver_obj.fields.density_3d
        xyz = SpatialCoordinate(self.solver_obj.mesh)
        self.expression = rho*(xyz[0]*uv[1] - xyz[1]*uv[0])
        self.mass = assemble(rho*dx)

    def __call__(self):
        if not hasattr(self, '_initialized') or self._initialized is False:
            self._initialize()
        val = assemble(self.expression*dx)/self.mass
        if self.initial_val is None:
            self.initial_val = val
        return (val, )

    def message_str(self, *args):
        line = 'angular momentum: {:16.10e}'.format(args[0])
        return line


class KineticEnergyCalculator(DiagnosticCallback):
    """
    Computes the total kinetic energy of the horizontal velocity field.

    Ke = 1/2 \int \rho * |u|**2 dx

    where \rho is the water density, and u the horizontal velocity.
    """
    name = 'kine'
    variable_names = ['kine']

    def _initialize(self):
        self.initial_val = None
        self._initialized = True
        uv = self.solver_obj.fields.uv_3d
        rho = self.solver_obj.fields.density_3d + rho0
        self.expression = 0.5*rho*(uv[0]*uv[0] + uv[1]*uv[1])

    def __call__(self):
        if not hasattr(self, '_initialized') or self._initialized is False:
            self._initialize()
        val = assemble(self.expression*dx)
        if self.initial_val is None:
            self.initial_val = val
        return (val, )

    def message_str(self, *args):
        line = 'kinetic energy: {:16.10e}'.format(args[0])
        return line


# set physical constants
rho0 = 1025.0
physical_constants['rho0'].assign(rho0)

reso = 'coarse'

outputdir = 'outputs_{:}'.format(reso)
layers = 7 if reso == 'coarse' else 30
mesh2d = Mesh('mesh_{:}.msh'.format(reso))
print_output('Loaded mesh ' + mesh2d.name)
dt = 25.0
t_end = 360 * 3600
t_export = 900.0
depth = 20.0
reynolds_number = 75.
viscosity = 'const'

temp_const = 10.0
salt_center = 33.75
salt_outside = 34.85

# bathymetry
P1_2d = FunctionSpace(mesh2d, 'CG', 1)
bathymetry_2d = Function(P1_2d, name='Bathymetry')
bathymetry_2d.assign(depth)

coriolis_2d = Function(P1_2d)
f0, beta = 1.15e-4, 0.0
coriolis_2d.interpolate(
    Expression('f0+beta*(x[1]-y_0)', f0=f0, beta=beta, y_0=0.0))

# compute horizontal viscosity
uscale = 1.0
delta_x = 1200.0 if reso == 'coarse' else 800.0
nu_scale = uscale * delta_x / reynolds_number
print_output('Mesh Reynolds number: {:}'.format(reynolds_number))
if viscosity == 'const':
    print_output('Viscosity: {:}'.format(nu_scale))

u_max = 1.0
w_max = 1.2e-2


# create solver
solver_obj = solver.FlowSolver(mesh2d, bathymetry_2d, layers)
options = solver_obj.options
options.element_family = 'dg-dg'
options.timestepper_type = 'leapfrog'
options.solve_salt = True
options.solve_temp = False
options.constant_temp = Constant(temp_const)
options.solve_vert_diffusion = False
options.use_bottom_friction = False
options.use_turbulence = False
options.use_turbulence_advection = False
# options.use_ale_moving_mesh = False
options.baroclinic = True
options.coriolis = coriolis_2d
options.uv_lax_friedrichs = None
options.tracer_lax_friedrichs = None
# options.h_diffusivity = Constant(50.0)
# options.h_viscosity = Constant(50.0)
options.v_viscosity = Constant(1.3e-6)  # background value
options.v_diffusivity = Constant(1.4e-7)  # background value
options.use_limiter_for_tracers = True
if viscosity == 'smag':
    options.smagorinsky_factor = Constant(1.0/np.sqrt(reynolds_number))
elif viscosity == 'const':
    options.h_viscosity = Constant(nu_scale)
else:
    raise Exception('Unknow viscosity type {:}'.format(viscosity))
options.t_export = t_export
options.t_end = t_end
options.outputdir = outputdir
options.u_advection = Constant(1.5)
options.check_vol_conservation_2d = True
options.check_vol_conservation_3d = True
options.check_salt_conservation = True
options.check_salt_overshoot = True
options.fields_to_export = ['uv_2d', 'elev_2d', 'uv_3d',
                            'w_3d', 'w_mesh_3d', 'salt_3d', 'density_3d',
                            'uv_dav_2d', 'uv_dav_3d', 'baroc_head_3d',
                            'baroc_head_2d']
options.fields_to_export_hdf5 = ['uv_2d', 'elev_2d', 'uv_3d',
                                 'w_3d', 'salt_3d', 'smag_visc_3d',
                                 'eddy_visc_3d', 'shear_freq_3d',
                                 'buoy_freq_3d', 'tke_3d', 'psi_3d',
                                 'eps_3d', 'len_3d']
options.equation_of_state = 'linear'
options.lin_equation_of_state_params = {
    'rho_ref': rho0,
    's_ref': 33.75,
    'th_ref': 5.0,
    'alpha': 0.0,
    'beta': 0.78,
}

solver_obj.add_callback(VorticityCalculator(solver_obj))
solver_obj.add_callback(AngularMomentumCalculator(solver_obj))
solver_obj.add_callback(KineticEnergyCalculator(solver_obj))

solver_obj.create_equations()
# assign initial salinity
# impose rho' = rho - 1025.0
salt_init3d = Function(solver_obj.function_spaces.P1, name='initial salinity')
salt_init3d.interpolate(Expression('s_0 + 1.1*pow((sqrt(x[0]*x[0] + x[1]*x[1])/1000/3 + (1.0-tanh(10*(x[2] + 10.0)))*0.5), 8)', s_0=salt_center))
# crop bad values
ix = salt_init3d.dat.data[:] > salt_outside
salt_init3d.dat.data[ix] = salt_outside

solver_obj.assign_initial_conditions(salt=salt_init3d)
solver_obj.iterate()
