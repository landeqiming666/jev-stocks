-- ; leading comment
CREATE TABLE "a;b" (value VARCHAR);
INSERT INTO "a;b" VALUES ('a;b'), ('it''s;fine');
/* ; outer /* ; nested */ ; */ INSERT INTO "a;b" VALUES ($tag$dollar;quote$tag$);
-- ; trailing comment
