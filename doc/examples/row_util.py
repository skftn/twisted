from twisted.enterprise import row


##################################################
########## Definitions of Row Classes ############
##################################################

def myRowFactory(rowClass, data, kw):
    newRow = rowClass()
    newRow.__dict__.update(kw)
    return newRow


class RoomRow(row.RowObject):
    rowColumns = [
        ("roomId",  "int"),
        ("town_id", "int"),
        ("name",    "varchar"),
        ("owner",   "varchar"),
        ("posx",    "int"),
        ("posy",    "int"),
        ("width",   "int"),
        ("height",  "int")
        ]
    rowKeyColumns    = [("roomId","int4")]
    rowTableName     = "testrooms"
    rowFactoryMethod = [myRowFactory]

    def __init__(self):
        self.furniture = []

    def addStuff(self, stuff):
        self.furniture.append(stuff)
        
    def moveTo(self, x, y):
        self.posx = x
        self.posy = y
        
    def __repr__(self):
        return "<Room #%s: %s (%s) (%s,%s)>" % (self.roomId, self.name, self.owner, self.posx, self.posy)

class FurnitureRow(row.RowObject):
    rowColumns      = [
        ("furnId", "int"),
        ("roomId", "int"),
        ("name",   "varchar"),
        ("posx",   "int"),
        ("posy",   "int")
        ]
    rowKeyColumns   = [("furnId","int4")]
    rowTableName    = "furniture"
    rowForeignKeys  = [("testrooms", [("roomId","int4")], [("roomId","int4")], "addStuff", 1) ]
    
    def __repr__(self):
        return "Furniture #%s: room #%s (%s) (%s,%s)" % (self.furnId, self.roomId, self.name, self.posx, self.posy)

class RugRow(row.RowObject):
    rowColumns       = [
        ("rugId",  "int"),
        ("roomId", "int"),
        ("name",   "varchar")
        ]
    rowKeyColumns    = [("rugId","int4")]
    rowTableName     = "rugs"
    rowFactoryMethod = [myRowFactory]
    rowForeignKeys   = [( "testrooms", [("roomId","int4")],[("roomId","int4")], "addStuff", 1) ]
    
    def __repr__(self):
        return "Rug %#s: room #%s, (%s)" % (self.rugId, self.roomId, self.name)

class LampRow(row.RowObject):
    rowColumns      = [
        ("lampId",   "int"),
        ("furnId",   "int"),
        ("furnName", "varchar"),
        ("lampName", "varchar")
        ]
    rowKeyColumns   = [("lampId","int4")]
    rowTableName    = "lamps"
    rowForeignKeys  = [("furniture", [("furnId","int4"),("furnName", "varchar")],
                      [("furnId","int4"),("name", "varchar")], None, 1) ]
                      # NOTE: this has no containerMethod so children will be added to "childRows"
    
    def __repr__(self):
        return "Lamp #%s" % self.lampId
