# routes/blacklist_api.py
from flask import Blueprint, request, jsonify, abort
from models.blacklist_model import SessionLocal, BlacklistShip

blacklist_api = Blueprint("blacklist_api", __name__)

# 取得所有黑名單
@blacklist_api.route("/blacklist_ships", methods=["GET"])
def get_blacklist_ships():
    session = SessionLocal()
    ships = session.query(BlacklistShip).order_by(BlacklistShip.id.desc()).all()

    data = [
        {
            "id": s.id,
            "name": s.name,
            "note": s.note,
            "created_at": s.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        }
        for s in ships
    ]

    session.close()
    return jsonify({"count": len(data), "items": data})


# 新增黑名單
@blacklist_api.route("/blacklist_ships", methods=["POST"])
def add_blacklist_ship():
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    note = (data.get("note") or "").strip() or None

    if not name:
        abort(400, "name is required")

    session = SessionLocal()
    try:
        ship = BlacklistShip(name=name, note=note)
        session.add(ship)
        session.commit()

        new_id = ship.id
        return jsonify({"message": "created", "id": new_id})

    except Exception as e:
        session.rollback()
        abort(500, str(e))

    finally:
        session.close()


# 刪除黑名單
@blacklist_api.route("/blacklist_ships/<int:sid>", methods=["DELETE"])
def delete_blacklist_ship(sid):
    session = SessionLocal()
    ship = session.query(BlacklistShip).filter_by(id=sid).first()

    if not ship:
        session.close()
        abort(404, "not found")

    try:
        session.delete(ship)
        session.commit()
        return jsonify({"message": "deleted"})

    except Exception as e:
        session.rollback()
        abort(500, str(e))

    finally:
        session.close()
