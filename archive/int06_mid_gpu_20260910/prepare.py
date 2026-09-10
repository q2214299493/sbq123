"""Prepare a bounded dual-model GPU request from the reviewed INT06-MID seed."""
from copy import deepcopy
import shutil

from archive.int06_mid_gpu_20260910.inspect_remote import BASE, ROOT
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.dual_model_ml_neb import _geometry_guard_evidence, _load_images, _load_request
from scripts.ts_strategy_engine.contract import load_contract
from scripts.ts_strategy_engine.path_evidence import validate_path_review

SOURCE = ROOT/'calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_migration_int06_to_mid_path_20260910'
PATH = SOURCE/'plan/path_candidate'
PARENT = ROOT/'calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/gpu_split_paths_dual_model_20260901'
REMOTE = '/home/sbq/sbq/aqcat25_ts_pilot/handoffs/int06_mid_ml_neb_20260910'


def main() -> None:
    assert validate_path_review(PATH/'path_review.json', PATH/'path_generation_report.json')[0]
    contract = load_contract(SOURCE/'contract.json')
    request = deepcopy(load_json_object(PARENT/'segment_01_IS_A_to_MID/work_to_gpu/request.json'))
    remote = load_json_object(BASE/'remote_inventory.json')
    for role in ('primary','secondary'):
        model = request['models'][role]
        observed = remote['models'][model['backend']]
        assert model['checkpoint_sha256'] == observed['sha256']
        assert model['remote_checkpoint_path'] == observed['path']
    package = BASE/'payload'
    package.mkdir(exist_ok=False)
    (package/'structures').mkdir()
    (package/'review').mkdir()
    (package/'runtime').mkdir()
    copies = {
        'reaction_contract.normalized.json':SOURCE/'contract.json',
        'review/path_review.json':PATH/'path_review.json',
        'review/path_generation_report.json':PATH/'path_generation_report.json',
        'review/exact_mic_geometry.json':PATH/'exact_mic_geometry.json',
        'review/dist.dat':PATH/'dist.dat',
        'review/movie.xyz':PATH/'movie.xyz',
        'review/vtst_commands.json':PATH/'vtst_commands.json',
        'review/path_review.png':SOURCE/'path_review.png',
    }
    for target, source in copies.items():
        shutil.copyfile(source,package/target)
    runtime_names = ['dual_model_ml_neb.py','dual_model_ml_neb_job.sh','aqcat25_ml_neb.py',
                     'mlip_same_structure_benchmark.py','artifact_io.py','aqcat25_handoff.py',
                     'aqcat25_mz73_env.sh','ml_sella_candidate.py']
    for name in runtime_names:
        shutil.copyfile(ROOT/'scripts'/name,package/'runtime'/name)
    request['request_id'] = contract['reaction_id']+'_gpu_20260910'
    request['source_plan'] = {'method':'unrestrained MatRIS ML-NEB then exact-fixed-path AQCat25 audit',
                              'source_request_sha256':sha256_file(PARENT/'segment_01_IS_A_to_MID/work_to_gpu/request.json'),
                              'reuse_scope':'model identities and established optimizer/geometry policies only'}
    request['source_seed_review'] = {'path':'review/path_review.json',
                                    'sha256':sha256_file(package/'review/path_review.json'),
                                    'review_status':'accepted_for_initial_geometry_only'}
    request['source_evidence_files'] = {name:sha256_file(package/name) for name in copies}
    request['reaction'] = {'reaction_id':contract['reaction_id'],
                           **{key:contract[key] for key in ('contract_sha256','atom_map_sha256','compatibility_sha256')},
                           'indexed_bond_changes':[], 'reaction_coordinates':contract['reaction_coordinates']}
    request['images'] = []
    for i in range(5):
        target = package/f'structures/{i:02d}.vasp'
        shutil.copyfile(PATH/f'{i:02d}/POSCAR',target)
        request['images'].append({'image':f'{i:02d}','path':f'structures/{i:02d}.vasp','sha256':sha256_file(target)})
    request['preconditioning']['purpose'] = 'reuse reviewed unrestrained INT06-MID five-frame seed'
    request['ordinary_ml_neb']['purpose'] = 'bounded unrestrained H50 surface migration; no ML-CI or Sella'
    # Record the site coordinate without imposing bond-making or monotonicity.
    coordinate = contract['reaction_coordinates'][0]
    request['geometry_guards']['monitored_bonds'] = [{
        'name':'H50_Fe39_site_contact','atoms_zero_based':[49,38],
        'important_interval_A':coordinate['important_interval_A'], 'minimum_internal_images':0,
    }]
    request['runtime_bindings'] = {name:sha256_file(package/'runtime'/name) for name in runtime_names}
    request['production_limits']['image_count'] = 5
    request['domain_validation'] = {
        'status':'uncalibrated_for_INT06_to_MID_prediction_only',
        'parent_request_sha256':request['source_plan']['source_request_sha256'],
        'quantitative_uncertainty_calibrated':False,
        'note':'No checkpoint promotion or transfer of prior O-H-domain validation to this H-migration interval.',
    }
    write_json_exclusive(package/'request.json',request)
    parsed = _load_request(package/'request.json')
    images = _load_images(parsed,package)
    geometry = _geometry_guard_evidence(images,parsed)
    assert geometry['passed'] and len(images)==5
    assert parsed['ordinary_ml_neb']['max_steps']==400
    assert parsed['ordinary_ml_neb']['ml_ci']=='off'
    assert parsed['fixed_atom_indices_zero_based']==list(range(18))
    write_json_exclusive(BASE/'local_preflight.json',{
        'status':'PASS','request_sha256':sha256_file(package/'request.json'),
        'geometry':geometry,'image_count':len(images), 'model_execution_performed':False,
        'scheduler_submission_performed':False,'remote_inventory_sha256':sha256_file(BASE/'remote_inventory.json'),
    })
    write_json_exclusive(BASE/'execution_plan.json',{
        'request_sha256':sha256_file(package/'request.json'),'remote_root':REMOTE,
        'scheduler_resources':parsed['scheduler_resources'],'ordinary_ml_neb':parsed['ordinary_ml_neb'],
        'authorization_status':'pending_exact_package_user_approval',
        'required_before_production':['remote_no_model_preflight','exact_package_user_authority',
                                      'current_owning_execution_gate_for_any_required_path_action',
                                      'duplicate_submission_reservation_check'],
        'vasp_submission_authorized':False,'automatic_retry':False,
    })
    (BASE/'.gitattributes').write_text('** -text whitespace=cr-at-eol\n*.vasp -whitespace\n**/movie.xyz -whitespace\n',encoding='ascii')
    print({'status':'PASS','images':len(images),'request_sha256':sha256_file(package/'request.json'),
           'max_step_A':geometry['maximum_single_movable_atom_step_A'],
           'resources':parsed['scheduler_resources']})


if __name__ == '__main__':
    main()
