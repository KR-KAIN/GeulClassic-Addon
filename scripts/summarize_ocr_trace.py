"""Summarize metadata-only JSONL timings without external packages."""
import json
import math
from pathlib import Path
import sys

def percentile(data,fraction):
    sorted_values=sorted(data)
    return sorted_values[max(0,math.ceil(len(sorted_values)*fraction)-1)] if sorted_values else None

def summarize(source):
    """Report measured frame statistics from the newest session only.

    Startup/session markers (schema=2) aren't frame measurements and must
    never be presented as fabricated zero-millisecond OCR samples.
    """
    rows=[]
    markers=[]
    for line in Path(source).read_text(encoding='utf-8-sig').splitlines():
        try:
            value=json.loads(line)
        except (ValueError,TypeError):
            continue
        if not isinstance(value,dict):continue
        if value.get('schema')==2:
            if value.get('event')=='session_start':
                rows=[];markers=[]
            markers.append(value)
        elif value.get('schema')==1:
            rows.append(value)
    if not rows:
        state=', '.join(str(m.get('event')) for m in markers) or 'no startup markers'
        return ('GEULCLASSIC OCR STAGE PROFILE SUMMARY\n'
                'Frames: 0 (NO MEASUREMENTS)\n'
                f'Session status: {state}\n'
                'Start the PROFILE EXPORT FIX application, enable chat OCR, '
                'then play for 3 minutes before exporting.\n')
    fields=[('cap_ms','Capture thread (capture + preprocessing)'),
            ('queue_wait_ms','Capture->OCR queue wait only'),
            ('pre_ms','OCR preprocessing / segmentation'),
            ('ocr_model_path_ms','OCR recognize and detector-recovery wall time'),
            ('post_ms','OCR+worker postprocessing and enqueue'),
            ('stage_total_ms','IncrementalChatOCR.detect full duration'),
            ('stage_recovery_detector_ms','Fallback full detector'),
            ('primary_ms','English recognition primary'),
            ('retry_ms','English recognition retry'),
            ('korean_ms','Korean recognition'),
            ('item_ocr_ms','Item linked OCR correction'),
            ('translation_queue_wait_p95_ms','Translation queue wait rolling p95')]
    out=['GEULCLASSIC OCR STAGE PROFILE SUMMARY',
         f'Frames: {len(rows)} (newest recorded session only)',
         'Times are elapsed milliseconds, not pure ONNX inference.',
         'p50/p95 include frames with a zero for unused stages.',
         'p50/p95(active) below include only calls where stage > 0.',
         'ocr_active_ms excludes cache-only frames.',
         '']
    for key,label in fields:
        nums=[float(r[key]) for r in rows if isinstance(r.get(key),(float,int))]
        if not nums:continue
        active=[x for x in nums if x>0]
        n=len(nums)
        out.append(f'{key} ({label}): count={n}, active={len(active)}, '
                   f'p50={percentile(nums,.5):.2f} p95={percentile(nums,.95):.2f} '
                   f'p99={percentile(nums,.99):.2f} max={max(nums):.2f}'
                   +(f' | active_p50={percentile(active,.5):.2f} '
                     f'active_p95={percentile(active,.95):.2f}' if active else ''))
    out.extend(['','OCR path utilization:'])
    for key in ('ocr_cached_frame','detector_recoveries','retry_rows','korean_rows','item_ocr_inputs'):
        positive=sum(1 for r in rows if (r.get(key) or 0)>0)
        out.append(f'  {key}: frames={positive}/{len(rows)} ({100*positive/len(rows):.1f}%)')
    # Record not only detector calls but WHY they were requested. Compound
    # reasons count under each component as well as under their exact label.
    from collections import defaultdict
    by_reason=defaultdict(list)
    by_component=defaultdict(list)
    for r in rows:
        reason=str(r.get('recovery_reasons','') or '')
        if not reason:
            continue
        by_reason[reason].append(r)
        for part in reason.split('+'):
            by_component[part].append(r)
    out.append('')
    out.append('Recovery reasons (requested frames, detector calls, total detector wall ms):')
    for label, group in sorted(by_reason.items(),key=lambda item:-len(item[1])):
        attempts=[r for r in group if int(r.get('detector_recoveries',0))>0]
        total_ms=sum(float(r.get('stage_recovery_detector_ms',0)) for r in attempts)
        blockers=sum(int(r.get('recovery_gate_blocked',0)) for r in group)
        caches=sum(int(r.get('recovery_cache_hit',0)) for r in group)
        positives=sum(int(r.get('recovery_rows_found',0)) for r in attempts)
        measured=[float(r.get('stage_recovery_detector_ms',0)) for r in attempts]
        mean=total_ms/len(measured) if measured else 0.0
        tail=percentile(measured,.95) if measured else 0.0
        out.append(f'  exact {label}: requested={len(group)}, calls={len(attempts)}, '
                   f'blocked={blockers}, cache_hits={caches}, '
                   f'rows_found={positives}, detector_ms_sum={total_ms:.2f}, '
                   f'detector_ms_avg={mean:.2f}, detector_ms_p95={tail:.2f}')
    for label, group in sorted(by_component.items()):
        attempts=[r for r in group if int(r.get('detector_recoveries',0))>0]
        total_ms=sum(float(r.get('stage_recovery_detector_ms',0)) for r in attempts)
        out.append(f'  component {label}: requested={len(group)}, calls={len(attempts)}, '
                   f'detector_ms_sum={total_ms:.2f}')
    blocked_counts={}
    for r in rows:
        reason=r.get('recovery_gate_block_reason')
        if reason:blocked_counts[reason]=blocked_counts.get(reason,0)+1
    if blocked_counts:
        out.append('  blocks_by_gate: '+', '.join(f'{k}={v}' for k,v in sorted(blocked_counts.items())))
    recover_count=sum(int(r.get('detector_recoveries',0)>0) for r in rows)
    recover_ratio=100.0*recover_count/len(rows)
    out.extend(['',f'Recovery frame ratio: {recover_count}/{len(rows)} = {recover_ratio:.2f}%',
                'Previously reported baseline: approx. 43% (user-supplied; not a replayed measurement)',
                f'Change against reported baseline: {recover_ratio-43.0:+.2f} percentage points',
                '', 'Input dimensions (maxima observed, in pixels):'])
    for name in ('input_width_px','input_height_px','input_bytes',
                 'rec_input_max_width_px','rec_input_max_height_px',
                 'korean_input_max_width_px','korean_input_max_height_px',
                 'item_input_max_width_px','item_input_max_height_px',
                 'detector_input_max_width_px','detector_input_max_height_px'):
        vals=[int(r[name]) for r in rows if isinstance(r.get(name),(float,int)) and r[name]>0]
        if vals:out.append(f'  {name}: max={max(vals)}')
    out.extend(['','Counts:'])
    for key in ('recognition_inputs','recognition_batches','detector_calls',
                'new_rows','cache_hits'):
        vals=[int(r.get(key,0)) for r in rows]
        out.append(f'  {key}: sum={sum(vals)}, max_per_frame={max(vals)}')
    # TTL experiment results are AFTER the physical-message ledger, not raw OCR.
    if any('ttl_trial_mode' in r for r in rows):
        from collections import Counter
        modes=Counter(str(r.get('ttl_trial_mode','unknown')) for r in rows)
        metric_keys=('ttl_candidates','ttl_short_allowed','ttl_long_allowed',
                     'ttl_extra_blocked','ttl_actual_blocked','ttl_visual_new_blocked',
                     'ttl_guard_suppressed','ttl_visual_ledger_suppressed',
                     'ttl_delivered_to_output','ttl_output_emitted_delta')
        out.extend(['', 'R8 2s vs 15s TTL experiment (post-visual-ledger candidate comparison):',
                    '  Modes: '+', '.join(f'{mode}={count} frames' for mode,count in sorted(modes.items())),
                    '  WARNING: R7 did NOT invoke SlidingChatDeduper.filter in live delivery.',
                    '  These are hypothetical TTL gate decisions; only ACTIVE mode affects output.',
                    '  Every incoming candidate already represents a new visual event, so TTL blocking may cause output misses.'])
        totals={k:sum(int(r.get(k,0)) for r in rows) for k in metric_keys}
        for k in metric_keys:out.append(f'  {k}: {totals[k]}')
        n=totals['ttl_candidates']
        if n:
            out.append(f'  2s shadow allow rate: {100*totals["ttl_short_allowed"]/n:.2f}%')
            out.append(f'  15s shadow allow rate: {100*totals["ttl_long_allowed"]/n:.2f}%')
            out.append(f'  15s extra blocks vs 2s: {100*totals["ttl_extra_blocked"]/n:.2f}% of visual-new candidates')
            out.append(f'  Post-ChannelGuard acceptance rate: {100*totals["ttl_delivered_to_output"]/n:.2f}% of visual-new candidates')
        out.append('  Short/long skipped totals above are candidate-filter counts, not R7 actual output suppression.')
        out.append('  ttl_output_emitted_delta counts emitted signals; async outputs can lag their OCR frame.')
        out.append('  ttl_delivered_to_output counts post-ChannelGuard candidates before translation; not all reach display.')
    out.extend(['','Top 10 slowest OCR frames (by stage_total_ms):'])
    top=sorted(enumerate(rows,1),key=lambda t:float(t[1].get('stage_total_ms',0)),reverse=True)[:10]
    for index,(i,r) in enumerate(top,1):
        components=['stage_total_ms','pre_ms','ocr_model_path_ms','post_ms',
                    'queue_wait_ms','stage_recovery_detector_ms','primary_ms',
                    'retry_ms','korean_ms','item_ocr_ms','new_rows',
                    'ocr_cached_frame','recovery_reasons','recovery_gate_blocked','recovery_rows_found',
                    'input_width_px','input_height_px']
        parts=', '.join(f'{k}={r.get(k,0)}' for k in components)
        out.append(f'  {index}. frame={i} {parts}')
    out.append('')
    return '\n'.join(out)

if __name__=='__main__':
    if len(sys.argv)!=3:
        print('usage: summarize_ocr_trace.py INPUT.jsonl OUTPUT.txt')
        raise SystemExit(2)
    Path(sys.argv[2]).write_text(summarize(sys.argv[1]),encoding='utf-8')
    print('Written summary: '+sys.argv[2])
