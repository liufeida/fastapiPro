from app.schemas.index import ResponseModel


class Execute:
    def response(self, data=None, message="success"):
        return ResponseModel(code=200, message=message, data=data)


Execute = Execute()
