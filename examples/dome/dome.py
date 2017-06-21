"""
DOME test case
==============

Initially the water column is linearly stratified with density difference of
2 kg/m3 in the deepest part of the domain.

In the embayment there is a geostrophically balanced inflow of 5e6 m3/s with
positive density anomaly 2 kg/m3.

Radiation boundary conditions are applied in the east and west open boundaries.

Typical mesh resolution is dx=10 km, 21 sigma levels [2]

[1] Ezer and Mellor (2004). A generalized coordinate ocean model and a
    comparison of the bottom boundary layer dynamics in terrain-following and
    in z-level grids. Ocean Modelling, 6(3-4):379-403.
    http://dx.doi.org/10.1016/S1463-5003(03)00026-X
[2] Burchard and Rennau (2008). Comparative quantification of physically and
    numerically induced mixing in ocean models. Ocean Modelling, 20(3):293-311.
    http://dx.doi.org/10.1016/j.ocemod.2007.10.003
[3] Legg et al. (2006). Comparison of entrainment in overflows simulated by
    z-coordinate, isopycnal and non-hydrostatic models. Ocean Modelling, 11(1-2):69-97.
"""
from thetis import *
import dome_setup as setup

comm = COMM_WORLD

physical_constants['rho0'] = setup.rho_0

reso_str = 'coarse'
delta_x_dict = {'normal': 4e3, 'coarse': 20e3}
n_layers_dict = {'normal': 12, 'coarse': 7}
n_layers = n_layers_dict[reso_str]
mesh2d = Mesh('mesh_{0:s}.msh'.format(reso_str))
print_output('Loaded mesh '+mesh2d.name)
t_end = 40 * 24 * 3600
t_export = 3 * 3600
outputdir = 'outputs_' + reso_str

delta_x = delta_x_dict[reso_str]
delta_z = setup.depth_lim[1]/n_layers
nnodes = mesh2d.topology.num_vertices()
ntriangles = mesh2d.topology.num_cells()
nprisms = ntriangles*n_layers

# bathymetry
P1_2d = FunctionSpace(mesh2d, 'CG', 1)
bathymetry_2d = Function(P1_2d, name='Bathymetry')
xy = SpatialCoordinate(mesh2d)
lin_bath_expr = (setup.depth_lim[1] - setup.depth_lim[0])/(setup.y_slope[1] - setup.y_slope[0])*(xy[1] - setup.y_slope[0]) + setup.depth_lim[0]
bathymetry_2d.interpolate(lin_bath_expr)
bathymetry_2d.dat.data[bathymetry_2d.dat.data > setup.depth_lim[0]] = setup.depth_lim[0]
bathymetry_2d.dat.data[bathymetry_2d.dat.data < setup.depth_lim[1]] = setup.depth_lim[1]

# estimate velocity / diffusivity scales
u_max_int = np.sqrt(setup.g/setup.rho_0*setup.delta_rho/setup.depth_lim[0])*setup.depth_lim[0]/np.pi
u_max = 3.5
w_max = 3e-2

# NOTE needs nonzero viscosity to remain stable (no surprize really)
# NOTE needs to estimate speed of internal waves to estimate dt ...

# compute horizontal viscosity
uscale = 2.0
reynolds_number = 25.0  # 400.0 corresponds to Legg et al (2006)
nu_scale = uscale * delta_x / reynolds_number

# create solver
solver_obj = solver.FlowSolver(mesh2d, bathymetry_2d, n_layers)
options = solver_obj.options
options.element_family = 'dg-dg'
outputdir += '_' + options.element_family
options.timestepper_type = 'ssprk22'
# options.timestepper_type = 'leapfrog'
options.solve_salinity = True
options.solve_temperature = True
options.solve_vert_diffusion = False
options.use_bottom_friction = False
options.use_ale_moving_mesh = True
options.baroclinic = True
options.use_lax_friedrichs_velocity = True
options.use_lax_friedrichs_tracer = True
options.coriolis = Constant(setup.f_0)
options.use_limiter_for_tracers = True
options.v_viscosity = Constant(1.0e-2)
options.h_viscosity = Constant(nu_scale)
options.h_diffusivity = None
options.use_quadratic_pressure = True
options.t_export = t_export
options.t_end = t_end
options.outputdir = outputdir
options.nu_viscosity = Constant(nu_scale)
options.u_advection = Constant(u_max)
options.w_advection = Constant(w_max)
options.check_temp_overshoot = True
options.check_salt_overshoot = True
options.fields_to_export = ['uv_2d', 'elev_2d', 'uv_3d',
                            'w_3d', 'w_mesh_3d', 'temp_3d', 'salt_3d',
                            'density_3d', 'uv_dav_2d', 'uv_dav_3d',
                            'baroc_head_3d',
                            'int_pg_3d', 'hcc_metric_3d']
options.equation_of_state = 'linear'
options.lin_equation_of_state_params = {
    'rho_ref': setup.rho_0,
    's_ref': setup.salt_const,
    'th_ref': setup.temp_lim[1],
    'alpha': setup.alpha,
    'beta': setup.beta,
}

solver_obj.create_function_spaces()

xyz = SpatialCoordinate(solver_obj.mesh)

# create additional fields for imposing inflow boudary conditions
temp_expr = (setup.temp_lim[1] - setup.temp_lim[0])*(setup.depth_lim[0] + xyz[2])/setup.depth_lim[0] + setup.temp_lim[0]
temp_init_3d = Function(solver_obj.function_spaces.H, name='inflow temperature')
temp_init_3d.interpolate(temp_expr)
# this is inefficient! find a way to do this without allocating fields
x_arr = Function(solver_obj.function_spaces.H).interpolate(xyz[0]).dat.data[:]
y_arr = Function(solver_obj.function_spaces.H).interpolate(xyz[1]).dat.data[:]
z_arr = Function(solver_obj.function_spaces.H).interpolate(xyz[2]).dat.data[:]
x_w_arr = x_arr - setup.bay_x_lim[0]
ix = y_arr > setup.basin_ly + 50e3  # assign only in the bay
temp_init_3d.dat.data[ix] = setup.temp_func(x_w_arr[ix], z_arr[ix])

# use salinity field as a passive tracer for tracking inflowing waters
salt_init_3d = Function(solver_obj.function_spaces.H, name='inflow salinity')
# mark waters T < 15.0 degC as 1.0, 0.0 otherwise
ix = y_arr > setup.basin_ly + 50e3  # assign only in the bay
salt_init_3d.dat.data[ix] = (setup.temp_lim[1] - setup.temp_func(x_w_arr[ix], z_arr[ix]))/(setup.temp_lim[1] - setup.temp_lim[0])

uv_inflow_3d = Function(solver_obj.function_spaces.P1DGv, name='inflow velocity')
uv_inflow_3d.dat.data[ix, 1] = setup.v_func(x_w_arr[ix], z_arr[ix])
uv_inflow_2d = Function(solver_obj.function_spaces.P1DGv_2d, name='inflow velocity')


def compute_depth_av_inflow(uv_inflow_3d, uv_inflow_2d):
    """Computes depth average of 3d field. Should only be called once."""
    tmp_inflow_3d = Function(solver_obj.function_spaces.P1DGv)
    inflow_averager = VerticalIntegrator(uv_inflow_3d,
                                         tmp_inflow_3d,
                                         bottom_to_top=True,
                                         bnd_value=Constant((0.0, 0.0, 0.0)),
                                         average=True,
                                         bathymetry=solver_obj.fields.bathymetry_3d,
                                         elevation=solver_obj.fields.elev_cg_3d)
    inflow_extract = SubFunctionExtractor(tmp_inflow_3d,
                                          uv_inflow_2d,
                                          boundary='top', elem_facet='top',
                                          elem_height=solver_obj.fields.v_elem_size_2d)
    inflow_averager.solve()
    inflow_extract.solve()


# compute total volume flux at inflow bnd
tot_inflow = abs(assemble(dot(uv_inflow_3d, FacetNormal(solver_obj.mesh))*ds_v(int(4))))

# set boundary conditions
symm_swe_bnd = {'symm': None}
radiation_swe_bnd = {'elev': Constant(0.0), 'uv': Constant((0, 0))}
outflow_swe_bnd = {'elev': Constant(0.0), 'flux': Constant(tot_inflow)}
inflow_swe_bnd = {'uv': uv_inflow_2d}
zero_swe_bnd = {'elev': Constant(0.0), 'uv': Constant((0, 0))}
inflow_salt_bnd = {'value': salt_init_3d}
inflow_temp_bnd = {'value': temp_init_3d}
symm_temp_bnd = {'symm': None}
zero_salt_bnd = {'value': Constant(0.0)}
inflow_uv_bnd = {'uv': uv_inflow_3d}
symm_uv_bnd = {'symm': None}
outflow_uv_bnd = {'flux': Constant(tot_inflow)}
zero_uv_bnd = {'uv': Constant((0, 0, 0))}

bnd_id_west = 1
bnd_id_east = 2
bnd_id_south = 3
bnd_id_inflow = 4
solver_obj.bnd_functions['shallow_water'] = {
    bnd_id_inflow: inflow_swe_bnd,
    bnd_id_west: outflow_swe_bnd,
    bnd_id_east: radiation_swe_bnd,
    bnd_id_south: radiation_swe_bnd,
}
solver_obj.bnd_functions['momentum'] = {
    bnd_id_inflow: inflow_uv_bnd,
    bnd_id_west: outflow_uv_bnd,
    bnd_id_east: zero_uv_bnd,
    bnd_id_south: zero_uv_bnd,
}
solver_obj.bnd_functions['temp'] = {
    bnd_id_inflow: inflow_temp_bnd,
    bnd_id_west: inflow_temp_bnd,
    bnd_id_east: inflow_temp_bnd,
    bnd_id_south: inflow_temp_bnd,
}
solver_obj.bnd_functions['salt'] = {
    bnd_id_inflow: inflow_salt_bnd,
    bnd_id_west: zero_salt_bnd,
    bnd_id_east: zero_salt_bnd,
    bnd_id_south: zero_salt_bnd,
}

solver_obj.create_equations()

compute_depth_av_inflow(uv_inflow_3d, uv_inflow_2d)
hcc_obj = Mesh3DConsistencyCalculator(solver_obj)
hcc_obj.solve()

print_output('Running DOME problem with options:')
print_output('Resolution: {:}'.format(reso_str))
print_output('Element family: {:}'.format(options.element_family))
print_output('Polynomial order: {:}'.format(options.polynomial_degree))
print_output('Reynolds number: {:}'.format(reynolds_number))
print_output('Number of cores: {:}'.format(comm.size))
print_output('Mesh resolution dx={:} nlayers={:} dz={:}'.format(delta_x, n_layers, delta_z))
print_output('Number of 2D nodes={:}, triangles={:}, prisms={:}'.format(nnodes, ntriangles, nprisms))
print_output('Tracer DOFs per core: {:}'.format(6*nprisms/comm.size))
hcc = solver_obj.fields.hcc_metric_3d.dat.data
print_output('HCC mesh consistency: {:} .. {:}'.format(hcc.min(), hcc.max()))
print_output('Horizontal viscosity: {:}'.format(nu_scale))
print_output('Internal wave speed: {:.3f}'.format(u_max_int))
print_output('Total inflow: {:.3f} Sv'.format(tot_inflow/1e6))
print_output('Exporting to {:}'.format(outputdir))


def show_uv_mag():
    uv = solver_obj.fields.uv_3d.dat.data
    print_output('uv: {:9.2e} .. {:9.2e}'.format(uv.min(), uv.max()))


solver_obj.assign_initial_conditions(temp=temp_init_3d, salt=salt_init_3d)
solver_obj.iterate(export_func=show_uv_mag)
