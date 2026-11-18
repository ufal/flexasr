// spoken-edit: the document's state in the page. The page keeps the list of operations made since the file was
// loaded (its undo stack); every change asks the server for the document as it would be with the list, and a save
// sends the list. Requests go one at a time.
var SE = window.SE = window.SE || {};
SE.model = (function () {
	var cfg, base, initial, data, ops = [], redo = [], chain = Promise.resolve();

	function post ( act, list ) {
		return fetch(cfg.base + "&act=" + act, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
			body: JSON.stringify({ ops: list, hash: base }) })
			.then(function ( r ) { return r.json().then(function ( j ) { if ( !r.ok || j.error ) throw new Error(j.error || ("error " + r.status)); return j; }); });
	}
	function queue ( fn ) {
		var p = chain.then(fn);
		chain = p.catch(function () {});
		return p;
	}
	return {
		init: function ( c, d ) { cfg = c; base = d.hash; initial = d; data = d; ops = []; redo = []; },
		data: function () { return data; },
		dirty: function () { return ops.length; },
		canUndo: function () { return ops.length > 0; },
		canRedo: function () { return redo.length > 0; },
		// make an operation; resolves with the new data, rejects with the reason it cannot be made
		run: function ( op ) {
			return queue(function () {
				return post("apply", ops.concat([op])).then(function ( d ) { ops.push(op); redo = []; data = d; return d; });
			});
		},
		undo: function () {
			if ( !ops.length ) return Promise.resolve(data);
			return queue(function () {
				var list = ops.slice(0, -1);
				var get = list.length ? post("apply", list) : Promise.resolve(initial);
				return get.then(function ( d ) { redo.push(ops.pop()); data = d; return d; });
			});
		},
		redo: function () {
			if ( !redo.length ) return Promise.resolve(data);
			return queue(function () {
				var op = redo[redo.length - 1];
				return post("apply", ops.concat([op])).then(function ( d ) { ops.push(redo.pop()); data = d; return d; });
			});
		},
		save: function () {
			return queue(function () {
				return post("save", ops).then(function ( d ) { base = d.hash; initial = d; data = d; ops = []; redo = []; return d; });
			});
		}
	};
})();
