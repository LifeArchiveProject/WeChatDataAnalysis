"""已分析覆盖统计的计数与查询规模回归。"""
import json

from wechat_decrypt_tool.ai.agent_workspace import Workspace
from wechat_decrypt_tool.ai.storage import AIStore


def test_saved_note_coverage_scales_without_changing_counts(tmp_path):
    def measure(size):
        store = AIStore(tmp_path / str(size))
        workspace = Workspace(store)
        run_id = 'run'
        sources = [f'{index:024x}' for index in range(size)]
        materials = [
            (run_id, source, 'group' if index == size - 1 else 'friend', index,
             source, json.dumps({'text': 'same'}))
            for index, source in enumerate(sources)
        ]
        notes = []
        for index, source in enumerate(sources):
            # 第 0 条有缺口；第 1 条重复覆盖。相同正文仍是不同消息。
            intervals = [(0, 2), (3, 4)] if index == 0 else (
                [(0, 4), (0, 4)] if index == 1 else [(0, 4)])
            for part, (start, end) in enumerate(intervals):
                notes.append((run_id, 1, f'note:{index:08d}:{part}', 'stage_note',
                              json.dumps({'covered': [{'source': source, 'start': start, 'end': end}]})))
        with store.connection() as db:
            db.executemany('INSERT INTO agent_material VALUES(?,?,?,?,?,?)', materials)
            db.executemany('INSERT INTO agent_piece VALUES(?,?,?,?,?)', notes)
            # 同 source 的其他任务与旧版本笔记不能算进本轮。
            db.execute('INSERT INTO agent_material VALUES(?,?,?,?,?,?)',
                       ('other', sources[0], 'foreign', 0, sources[0], json.dumps({'text': 'same'})))
            db.execute('INSERT INTO agent_piece VALUES(?,?,?,?,?)',
                       ('other', 1, 'foreign-note', 'stage_note',
                        json.dumps({'covered': [{'source': sources[0], 'start': 0, 'end': 4}]})))
            db.execute('INSERT INTO agent_piece VALUES(?,?,?,?,?)',
                       (run_id, 2, 'old-version', 'stage_note',
                        json.dumps({'covered': [{'source': sources[0], 'start': 0, 'end': 4}]})))

            steps = 0

            def progress():
                nonlocal steps
                steps += 1
                return 0

            db.set_progress_handler(progress, 1000)
            try:
                counts, segments = workspace.saved_note_coverage(db, run_id, 1)
            finally:
                db.set_progress_handler(None, 0)

        assert counts == {'friend': size - 2, 'group': 1}
        assert segments == size + 2
        return steps

    small, large = measure(100), measure(1000)
    # 数据量放大十倍，不应重复交叉扫描整份原文和覆盖清单。
    assert large < small * 25, (small, large)
