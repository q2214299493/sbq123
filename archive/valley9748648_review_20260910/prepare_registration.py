"""Prepare one reviewed, append-only INT06 batch; never apply it implicitly."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.adsmind_lite.evidence_lifecycle import require_transferable, review_subject, text_digest
from scripts.artifact_io import sha256_file, sha256_json, write_json_exclusive

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / 'calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_migration1357_valley06_relax_20260909'
DEST = PACKAGE / 'completed_review_20260910'
CID = 'fe110_h_migration1357_valley06_relax_9748648'
JOB = 'lsf_sunboquan_9748648'


def main() -> None:
    def load(name):
        return json.loads((DEST/name).read_text(encoding='utf-8'))
    parsed, scheduler, registry = [load(name) for name in ('parsed_review_evidence.json','scheduler_and_hashes.json','registry_sources.json')]
    report = ROOT/'docs/reviews/valley9748648_accepted_20260910.md'
    now = datetime.now(timezone.utc).isoformat()
    source_compatibility = registry['parent_compatibility']
    compatibility = json.loads(source_compatibility['compatibility_json'])
    assert sha256_json(compatibility) == source_compatibility['compatibility_fingerprint']
    validation = {'owner':'vasp_relaxation','directory':str(DEST),'source_files':
                  {name:sha256_file(DEST/name) for name in ('INCAR','POSCAR','CONTCAR','OUTCAR','OSZICAR')},
                  'geometry_review_file':str(report),'geometry_review_sha256':sha256_file(report),
                  'parsed_review_sha256':sha256_file(DEST/'parsed_review_evidence.json')}
    result = {'result_id':CID+'_final_toten','calculation_id':CID,'result_name':'final_toten',
              'numeric_value':parsed['outcar']['final_TOTEN_eV'],'unit':'eV',
              'reference_convention':compatibility['final_energy_convention'],
              'source_file_id':CID+'_OUTCAR_final','source_locator':'final free energy TOTEN',
              'extraction_method':'VASP relaxation owning gate and final OUTCAR parser',
              'validation_status':'accepted_compatible_final_energy','created_at':now,
              'uncertainty_text':'No ZPE/entropy/Hessian verification or global-minimum claim.',
              'notes':'INT06: intact C2HO* plus separate H50 on Fe38/40/41; accepted mapped migration endpoint, not a TS.'}
    snapshot = report.read_text(encoding='utf-8')
    reference = str(report)
    evidence = {'claim':{'id':CID+'_reviewed_toten','type':'calculated_result',
                         'statement':'Converged, geometry-reviewed compatible VASP final TOTEN for INT06.',
                         'source_reference':reference,'status':'reviewed','evidence_relationship':'direct_local_calculation',
                         'scope':'registry_acceptance','domain':'adsorption_workflow','compatibility':compatibility,
                         'result_sha256':sha256_json(result),'validation_sha256':sha256_json(validation)},
                'source':{'identity':'VASP9748648 final relaxation and Codex scientific review','reference':reference,
                          'retrieved_at':scheduler['observed_at'],'snapshot':{'text':snapshot,'sha256':text_digest(snapshot)},
                          'immutable_reference':reference+'#sha256='+text_digest(snapshot)},
                'content':{'text':snapshot,'start':0,'end':len(snapshot),'sha256':text_digest(snapshot)}}
    evidence['review']={'reviewer':'Codex','reviewed_at':now,'decision':'accepted','scope':'registry_acceptance',
                        'subject_sha256':review_subject(evidence)}
    evidence['transfer']={'review_sha256':sha256_json(evidence['review']),'domain':'adsorption_workflow','compatibility':compatibility}
    require_transferable(evidence,{'domain':'adsorption_workflow','scope':'registry_acceptance','compatibility':compatibility})
    remote = json.loads((PACKAGE/'submission_record.json').read_text())['remote_dir']
    paths = [(name,DEST/name,'output') for name in ('OUTCAR','OSZICAR','CONTCAR')]
    paths += [(name,DEST/name,'validation') for name in ('scheduler_and_hashes.json','parsed_review_evidence.json','registry_sources.json')]
    paths += [('scientific_review',report,'review'),('collection_script',Path(__file__).with_name('review.py'),'analysis_script')]
    files = []
    for label,path,role in paths:
        files.append({'file_id':CID+'_'+label.replace('.','_')+'_final','calculation_id':CID,'job_record_id':JOB,
                      'role':role,'filename':path.name,'local_path':str(path),'remote_path':remote+'/'+label if role=='output' else None,
                      'storage_mode':'local_and_remote' if role=='output' else 'local','byte_size':path.stat().st_size,
                      'sha256':sha256_file(path),'existence_status':'confirmed',
                      'notes':'Hash-bound completion evidence; original inputs and immutable submission records preserved.'})
    batch = {'schema_version':1,'document_kind':'calculation_registry_batch','batch_id':'valley9748648_completion_20260910',
             'created_at':now,'reviewer':'Codex','reason':'User-authorized completion review and registration of INT06; no TS/barrier/Excel promotion.',
             'rows':{'files':files,'results':[result],
                     'calculation_compatibility':[{**source_compatibility,'calculation_id':CID,'reviewer':'Codex','reviewed_at':now}],
                     'job_status_history':[{'job_record_id':JOB,'scheduler_status':'DONE','scientific_status':'Converged and geometry reviewed',
                                            'checked_at':scheduler['observed_at'],'source_command':scheduler['source_command'],
                                            'source_text':scheduler['raw_stdout'],'reviewer':'Codex','notes':'79 steps; ordinary relaxation, not TS.'}],
                     'reviews':[{'review_id':CID+'_scientific_review_20260910','calculation_id':CID,'review_type':'adsorption_completion',
                                 'decision':'accepted','reviewer':'Codex','reviewed_at':now,'evidence':json.dumps(validation,sort_keys=True),
                                 'reason':'Normal/electronic/force convergence; intact C2HO plus H50; fixed layer and compatible branch preserved; nonduplicate under identity mapping. No full Hessian claim.'}]},
             'workflow_status_changes':[{'status_change_id':CID+'_accepted_20260910','calculation_id':CID,
                                         'expected_workflow_status':registry['calculation']['workflow_status'],'new_workflow_status':'accepted',
                                         'changed_at':now,'reviewer':'Codex','reason':'Owning relaxation/geometry review accepted INT06 and final TOTEN.'}],
             'result_provenance':{result['result_id']:{'type':'calculated_result','registry_stage':'accepted_result',
                                                    'evidence':evidence,'scientific_validation':validation}}}
    write_json_exclusive(DEST/'registry_batch.json',batch)
    print(json.dumps({'batch':str(DEST/'registry_batch.json'),'rows':{k:len(v) for k,v in batch['rows'].items()},
                      'result':result['result_id'],'energy_eV':result['numeric_value']}))


if __name__ == '__main__':
    main()
