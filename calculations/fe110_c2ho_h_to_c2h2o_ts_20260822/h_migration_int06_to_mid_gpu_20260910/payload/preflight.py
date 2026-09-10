"""Verify the staged request, code and geometry without loading either model."""
import json
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    sys.path.insert(0, str(ROOT/'runtime'))
    from artifact_io import load_json_object, sha256_file
    from dual_model_ml_neb import _geometry_guard_evidence, _load_images, _load_request, _verify_checkpoint

    manifest = load_json_object(ROOT/'payload_manifest.json')
    for name, digest in manifest['files'].items():
        path = (ROOT/name).resolve()
        assert path.is_relative_to(ROOT) and sha256_file(path) == digest, name
    request = _load_request(ROOT/'request.json')
    assert sha256_file(ROOT/'request.json') == manifest['request_sha256']
    for name, digest in request['runtime_bindings'].items():
        assert sha256_file(ROOT/'runtime'/name) == digest, name
    for name, digest in request['source_evidence_files'].items():
        assert sha256_file(ROOT/name) == digest, name
    images = _load_images(request, ROOT)
    geometry = _geometry_guard_evidence(images, request)
    assert geometry['passed'] and len(images) == 5
    assert request['preconditioning']['enabled'] is False
    assert not request['restraint_release']['stages']
    assert request['ordinary_ml_neb']['ml_ci'] == 'off'
    assert not request['production_limits']['production_submission_authorized']
    assert 'sella_refinement' not in request
    assert not request['automatic_vasp_submission']
    if socket.gethostname() == 'MZ73':
        for role in ('primary','secondary'):
            model = request['models'][role]
            _verify_checkpoint(Path(model['remote_checkpoint_path']),model['checkpoint_sha256'],role)
    print(json.dumps({'status':'PASS','hostname':socket.gethostname(),
                      'request_sha256':manifest['request_sha256'],
                      'payload_manifest_sha256':sha256_file(ROOT/'payload_manifest.json'),
                      'file_count':len(manifest['files']),'image_count':len(images),
                      'maximum_adjacent_rmsd_A':geometry['maximum_adjacent_rmsd_A'],
                      'maximum_single_movable_atom_step_A':geometry['maximum_single_movable_atom_step_A'],
                      'model_execution_performed':False,'scheduler_submission_performed':False}))


if __name__ == '__main__':
    main()
