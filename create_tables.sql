CREATE TABLE IF NOT EXISTS RESEARCHER (
   ResearcherID SERIAL UNIQUE NOT NULL,
   RName VARCHAR ( 250 ) NOT NULL,
	RLastName VARCHAR ( 250 ) NOT NULL,
	ORCHID integer,
	RMail VARCHAR ( 250 ),
	RPhone VARCHAR ( 250 ),
	RWebsite VARCHAR ( 250 ),
	RAddress VARCHAR ( 200 ),
	PRIMARY KEY (ResearcherID)
);
CREATE TABLE IF NOT EXISTS SERVICE (
	ServiceID SERIAL UNIQUE NOT NULL,
    SWhere VARCHAR ( 250 ),
	SRole VARCHAR ( 250 ),
	SYear integer,
	ResearcherID integer NOT NULL,
	FOREIGN KEY (ResearcherID)
    REFERENCES RESEARCHER (ResearcherID),
	PRIMARY KEY (ResearcherID, ServiceID)
);
CREATE TABLE IF NOT EXISTS AWARD (
    AwardID SERIAL UNIQUE NOT NULL,
    AName VARCHAR ( 2500 ) NOT NULL,
	AYear integer,
	ResearcherID integer NOT NULL,
	FOREIGN KEY (ResearcherID)
    REFERENCES RESEARCHER (ResearcherID),
	PRIMARY KEY (ResearcherID, AwardID)
);
CREATE TABLE IF NOT EXISTS GIVEN_COURSE (
    CourseID SERIAL UNIQUE NOT NULL,
    CName VARCHAR ( 250 ) NOT NULL,
	Code VARCHAR ( 20 ) NOT NULL,
	CYear integer,
	CSemester VARCHAR ( 20 ) ,
    ResearcherID integer NOT NULL,
	FOREIGN KEY (ResearcherID)
    REFERENCES RESEARCHER (ResearcherID),
	PRIMARY KEY (ResearcherID, CourseID)
);
CREATE TABLE IF NOT EXISTS SKILL (
    SkillID SERIAL UNIQUE NOT NULL,
    SName VARCHAR ( 250 ) NOT NULL,
	ProficiencyLevel integer,
	ResearcherID integer NOT NULL, 
	FOREIGN KEY (ResearcherID)
    REFERENCES RESEARCHER (ResearcherID),
	PRIMARY KEY (ResearcherID, SkillID)
);

CREATE TABLE IF NOT EXISTS PUBLICATION (
	PublicationID SERIAL UNIQUE NOT NULL ,
    PTitle VARCHAR ( 500 ) NOT NULL,
	PYear VARCHAR( 20 ),
    PType VARCHAR ( 250 ),
	Venue VARCHAR ( 500 ),
	DOI integer,
	ScholarURL VARCHAR ( 520 ),
	BibTex VARCHAR ( 2500 ),
	PRIMARY KEY (PublicationID)

);
CREATE TABLE IF NOT EXISTS SUPERVISED_THESIS (
    SupervisedThesisID SERIAL UNIQUE NOT NULL,
    STName VARCHAR ( 250 ),
	STLastName VARCHAR ( 250 ),
	STDegree VARCHAR ( 20 ),
	Code integer,
	CYear integer,
	CSemester VARCHAR ( 20 ),
	ResearcherID integer NOT NULL, 
	PublicationID integer NOT NULL, 
	FOREIGN KEY (ResearcherID)
    REFERENCES RESEARCHER (ResearcherID),
	FOREIGN KEY (PublicationID)
    REFERENCES PUBLICATION (PublicationID),
	PRIMARY KEY (ResearcherID, SupervisedThesisID)

);
CREATE TABLE IF NOT EXISTS CO_AUTHOR (
	PublicationID integer  NOT NULL ,
	ResearcherID integer  NOT NULL, 
	FOREIGN KEY (PublicationID)
    REFERENCES PUBLICATION (PublicationID),
	FOREIGN KEY (ResearcherID)
    REFERENCES RESEARCHER (ResearcherID),
	PRIMARY KEY (ResearcherID, PublicationID)

);
CREATE TABLE IF NOT EXISTS PHRASE (
	PhraseID SERIAL UNIQUE NOT NULL ,
	PName VARCHAR ( 520 ) NOT NULL,
	PRIMARY KEY (PhraseID)

);
CREATE TABLE IF NOT EXISTS INTEREST (
	ResearcherID integer  NOT NULL ,
	PhraseID integer  NOT NULL, 
	FOREIGN KEY (PhraseID)
    REFERENCES PHRASE (PhraseID),
	FOREIGN KEY (ResearcherID)
    REFERENCES RESEARCHER (ResearcherID),
	PRIMARY KEY (ResearcherID, PhraseID)

);
CREATE TABLE IF NOT EXISTS ORGANIZATION (
    OrganizationID SERIAL UNIQUE NOT NULL,
    OName VARCHAR ( 250 ) NOT NULL,
	OCity VARCHAR ( 250 ),
	OState VARCHAR ( 250 ),
	OCountry VARCHAR ( 250 ),
	PRIMARY KEY (OrganizationID)

);
CREATE TABLE IF NOT EXISTS WORK (
	WorkID SERIAL UNIQUE NOT NULL,
	ResearcherID integer  NOT NULL ,
	OrganizationID integer  NOT NULL, 
	WTitle VARCHAR ( 250 ),
	WDepartment VARCHAR ( 250 ),
	StartYear integer,
	EndYear integer,
	FOREIGN KEY (OrganizationID)
    REFERENCES ORGANIZATION (OrganizationID),
	FOREIGN KEY (ResearcherID)
    REFERENCES RESEARCHER (ResearcherID),
	PRIMARY KEY (WorkID)

);

CREATE TABLE IF NOT EXISTS EDUCATION (
	EducationID SERIAL UNIQUE NOT NULL,
	ResearcherID integer  NOT NULL ,
	OrganizationID integer  NOT NULL, 
	EDegree VARCHAR ( 250 ),
	EDepartment VARCHAR ( 250 ),
	StartYear integer,
	EndYear integer,
	FOREIGN KEY (OrganizationID)
    REFERENCES ORGANIZATION (OrganizationID),
	FOREIGN KEY (ResearcherID)
    REFERENCES RESEARCHER (ResearcherID),
	PRIMARY KEY (EducationID)

);