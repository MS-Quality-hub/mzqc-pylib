__author__ = 'walzer'
import json
import re
import logging
from datetime import datetime
from typing import List,Dict,Union,Any
import numpy as np
import pandas as pd

#int
#str
#float
FloatVector = List[float]
IntVector = List[int]
StringVector = List[str]
FloatMatrix = List[FloatVector]
IntMatrix = List[IntVector]
StringMatrix = List[StringVector]
#Table = Dict[str,Union(FloatVector,IntVector,StringVector)]
Table = Dict[str,List]

class JsonSerialisable(object):
    """
    JsonSerialisable Main structure template for mzQC objects

    Sets the foundation for a mzQC object to be readily (de-)serialisable with standard 
    python json handling code. Facilitates reading and writing of complex objects.

    """
    mappings: Dict[str, Any] = dict()

    @staticmethod
    def time_helper(da:str) -> datetime:
        """
        time_helper Helper method for ISO8601 string of various length consumption 

        Used on JSON datetime object string representation will handle length and return
        python datetime objects. JSON-schema actually follows 
        https://www.rfc-editor.org/rfc/rfc3339.html#section-5.6 which is a little more 
        stringent subset of ISO8601. 

        Parameters
        ----------
        da : str
            JSON datetime object string representation

        Returns
        -------
        datetime
            Python datetime object including the same amount detail provided 
        """
        try:
            dt = pd.to_datetime(da)
        except Exception as exc:
            raise ValueError(f"Unknown string format: {da}") from exc
        return dt

    @classmethod
    def class_mapper(classself, d):
        """
        class_mapper Maps incoming objects to their respective definition

        Allows every registered object to 'know' its type map incuding recursing into 
        its attributes. Can be used as object_hook in the json load process.
        
        Parameters
        ----------
        classself : self
            The objects class self
        d : dict
            The dictionary mapping attributes

        Returns
        -------
        class object
            Returns an object of the 'outer-most' class 

        Raises
        ------
        ValueError
            If expected date strings are invalid.
        """
        maxcls: Any = None
        exmax: int = 0
        for keys, cls in classself.mappings.items():
            if keys.issuperset(d.keys()):
                nx = len(set(d.keys()).intersection(set(keys)))
                if nx > exmax:
                    maxcls = cls
                    exmax = nx

        if maxcls is not None:
            return maxcls(**d)
        else:
            if {'creationDate': None}.keys() == d.keys():
                try:
                    return JsonSerialisable.time_helper(d['creationDate'])
                except ValueError as exc:
                    raise ValueError(f"It appears the creationDate of your file is not of ISO 8601 format including time to the second: {d['creationDate']}") from exc
            else:
                # raise ValueError('Unable to find a matching class for object: {d} (keys: {k})' .format(d=d,k=d.keys()))
                return d

    @classmethod
    def complex_handler(classself, obj):
        """
        complex_handler Handles the in-depth serialisations necessary

        Facilitates the correct serialisation for each type of object (within 
        the registered mzQC JsonSerialisable context) through possible 
        serialisation specialisation by way of object type. If objects behave 
        like dictionaries, but are complex classes (like all pymzqc obj),
        the dict needs to be returned as classical dict in order to serialise.

        Parameters
        ----------
        classself : self
            The objects class self
        obj : object
            The object to be deserialised

        Returns
        -------
        obj
            The correct object deconstruction into its deserialisable bits

        Raises
        ------
        TypeError
            In case a given object cannot be serialised with the given set of functionalities.
        """
        if isinstance(obj, datetime):
            logging.debug("serialisation specialisation dates: "+str(obj))
            if obj.tzinfo:
                return obj.isoformat().replace('+00:00','Z')
            else:  #assume local time is UTC, the standard requires RFC3339 after all (see specification)
                return obj.isoformat()+('Z')

        if 'numpy' in str(type(obj)):
            logging.debug("serialisation specialisation np.dtypes: "+str(obj))
            if isinstance(obj,np.ndarray):
                return obj.tolist()
            return obj.item()

        # needs to be last
        if hasattr(obj, '__dict__'):
            return {k:v for k,v in obj.__dict__.items() if v is not None and v != ""}

        raise TypeError(f"Object of type {type(obj)} with value {repr(obj)} is not JSON (de)serializable.")

    @classmethod
    def register(classself, cls):
        """
        register The method for class registration in the class mapping process

        Each registered class gets mapped.

        Parameters
        ----------
        classself : self
            the objects class self
        cls : object
            the class type

        Returns
        -------
        cls
            the class type
        """
        classself.mappings[frozenset(tuple([attr for attr, val in cls().__dict__.items()]))] = cls
        return cls

    @classmethod
    def to_json(classself, obj, readability=0, complete=True):
        """
        to_json main method for serialisation

        Parameters
        ----------
        classself : self
            The objects class self
        obj : object
            The object to be serialised
        readability : int, optional
            The indentation level, by default 0 (=no indentation, 
            1=minor indentation on MZQC objects, >1 heavy indentation for max. 
            human readability)
        complete: bool, optional 
            Flag to indicate if the object is to be left without the 
            enclosing `mzQC` key or if the JSON is to be amended to full 
            schema compliance (default).

        Returns
        -------
        str
            The serialisation result
        """
        if readability==0:
            ret = json.dumps(obj.__dict__ if isinstance(obj, MzQcFile) else
                             obj, default=classself.complex_handler)
        elif readability == 1:
            ret = json.dumps(obj.__dict__ if isinstance(obj, MzQcFile) else
                             obj, default=classself.complex_handler,
                             indent=2, cls=MzqcJSONEncoder)
        else:
            ret = json.dumps(obj.__dict__ if isinstance(obj, MzQcFile) else
                             obj, default=classself.complex_handler, indent=4)
        #remove empty run/setQualities and other optinal and empty elements, return with mzqc root,
        ret = re.sub(r'(\"setQualities\"\:\s+\[\s*\][,]*)|(\"runQualities\"\:\s+\[\s*\][,]*)|([,]*\s+\"fileProperties\"\:\s+\[\s*\][,]*)', "", ret)
        ret = re.sub(r'(\s*\"contactName\"\:\s+"",)|(\s*\"contactAddress\"\:\s+"",)|(\s*\"description\"\:\s+"",)', "", ret)
        ret = f"{{\"mzQC\": \n{ret} \n}}" if complete else ret
        return ret

    @classmethod
    def from_json(classself, json_str, complete=False):
        """
        from_json main method for deserialisation

        Accounts for neccessary object rectification due to same-attribute 
        class footprints. N.B.: for this to work the class init variables must
        be same name as the corresponding member attributes (self). 

        Parameters
        ----------
        classself : self
            The objects class self
        json_str : str
            The JSON string to be deserialised
        complete : bool, optional
            Flag to indicate if the whole JSON is to be returned deserialised, 
            or just the `mzQC` entry (default).

        Returns
        -------
        MzQcFile object
            The deserialised JSON string
        """
        if isinstance(json_str, str):
            j = json.loads(json_str, object_hook=classself.class_mapper)
        else:  # assume it is a IO wrapper
            j = json.load(json_str, object_hook=classself.class_mapper)
        if not(complete) and 'mzQC' in j.keys():
            j = j['mzQC']
        return rectify(j)


def rectify(obj):
    """
    rectify Rectifies objects according to their position in the local hierarchy

    Carries out the neccessary object rectification due to same-attribute class footprints.
    Rectification depends on the object position in the local object hierarchy.

    Parameters
    ----------
    obj : object
        The object to be rectified

    Returns
    -------
    object
        The rectified object
    """
    static_list_typemap = {'runQualities': RunQuality, 'setQualities': SetQuality,
                           'controlledVocabularies': ControlledVocabulary,
                           'qualityMetrics': QualityMetric,
                           'inputFiles': InputFile,
                           'analysisSoftware': AnalysisSoftware,
                           'fileProperties': CvParameter}
    static_singlet_typemap = {'fileFormat': CvParameter, 'metadata': MetaDataParameters}
    if hasattr(obj, '__dict__'):
        for k,v in obj.__dict__.items():
            if k in static_list_typemap.keys():
                v[:] = [rectify((static_list_typemap[k])(**i.__dict__ if hasattr(i, '__dict__') else i)) for i in v]
            elif k in static_singlet_typemap.keys():
                k = rectify((static_singlet_typemap[k])(**v.__dict__ if hasattr(v, '__dict__') else v))
            else:
                rectify(v)
    elif isinstance(obj, dict):
        for k,v in obj.items():
            rectify(v)
    return obj


class MzqcJSONEncoder(json.JSONEncoder):
    """
    MzqcJSONEncoder The encoder used to facilitate indented encoding 

    Handles the string encoding and formatting of the serialised objects.
    """
    def iterencode(self, o, _one_shot=False):
        indent_level = 0
        value_scope = False
        for s in super(MzqcJSONEncoder, self).iterencode(o, _one_shot=_one_shot):
            if value_scope and indent_level == 0 and s.startswith('}'):
                value_scope = False
            elif s.startswith('"value"'):
                value_scope = True
            if 0 < indent_level:
                s = s.replace('\n', '').rstrip().lstrip()
                if s.startswith(','):
                    s = ',' + s[1:].lstrip()
            if s.startswith('[') and value_scope:
                indent_level += 1
            if s.endswith(']') and value_scope:
                indent_level -= 1
                s = s.replace(']', '\n'+' '*self.indent*6+']').rstrip()
            yield s


class JsonObject(object):
    """
    JsonObject Proxy object for better integration of mzQC objects

    Useful for testing and validity checks as __eq__ is overridden to compare all 
    attributes as well.

    """
    def __eq__(self, other):
        """
        __eq__ Overrides the default implementation

        Compare all attributes as well.

        Parameters
        ----------
        other : object

        Returns
        -------
        bool
            False if the two objects are not of the same class or any of the attributes differ
        """
        if isinstance(other, __class__):
            # TODO find difference in keys and check whether they are None or "" in the other or vice versa
            snn = [k for k,v in self.__dict__.items() if (not v is None and not v == "")]
            onn = [k for k,v in other.__dict__.items() if (not v is None and not v == "")]
            if set(snn) == set(onn):
                return all([self.__getattribute__(attr) == other.__getattribute__(attr) for attr in self.__dict__.keys()])
        return False

@JsonSerialisable.register
class ControlledVocabulary(JsonObject):
    """
    ControlledVocabulary Object representation for mzQC schema type ControlledVocabulary

    """
    def __init__(self, name: str="", uri: str="", version: str=""):
        self.name = name  # required
        self.uri = uri  # required
        self.version = version  # optional

@JsonSerialisable.register
class CvParameter(JsonObject):
    """
    CvParameter Object representation for mzQC schema type CvParameter

    """
    def __init__(self, accession: str="",
                       name: str="",
                       description: str="",
                       value: Union[int,str,float,IntVector,StringVector,FloatVector,IntMatrix,StringMatrix,FloatMatrix,Table, None]=None,
                       unit: str=""):
        self.accession = accession  # required "pattern": "^[A-Z]+:[0-9]{7}$"
        self.name = name  # required
        self.description = description  # optional, "pattern": "^[A-Z]+$"
        self.value = value  # optional
        self.unit = unit  # optional, IMO this should be accession only, not annother cvParam

@JsonSerialisable.register
class AnalysisSoftware(CvParameter):
    """
    AnalysisSoftware Object representation for mzQC schema type AnalysisSoftware

    """
    def __init__(self, accession: str="",
                       name: str="",
                       description: str="",
                       value: str="",
                       unit: str="",
                       version: str = "",
                       uri: str = ""):
        super().__init__(accession, name, description, value, unit)  # optional, this will set None to optional omitted arguments
        self.version = version  # required
        self.uri = uri  # required

@JsonSerialisable.register
class InputFile(JsonObject):
    """
    InputFile Object representation for mzQC schema type InputFile

    """
    def __init__(self, location: str = "",
                    name: str = "",
                    fileFormat: CvParameter = None,
                    fileProperties: List[CvParameter] = None):
        self.location = location  # required , uri
        self.name = name  # required , string (doubles as internal and external ref anchor?)
        self.fileFormat = fileFormat  # required , cvParam
        self.fileProperties = [] if fileProperties is None else fileProperties  # optional, cvParam, at least one item

@JsonSerialisable.register
class MetaDataParameters(JsonObject):
    """
    MetaDataParameters Object representation for mzQC schema type MetaDataParameters

    """
    def __init__(self,
                    # fileProvenance: str="",
                    # cv_params: List[CvParameter] = None ,
                    label: str = "",
                    inputFiles: List[InputFile] = None,
                    analysisSoftware: List[AnalysisSoftware]=None
                ):
        # self.fileProvenance = fileProvenance  # not in schema
        # self.cv_params = [] if cv_params is None else cv_params  # not in schema, IMO should be in there
        self.label = label  # optional
        self.inputFiles =  [] if inputFiles is None else inputFiles  # required
        self.analysisSoftware = [] if analysisSoftware is None else analysisSoftware  # required

@JsonSerialisable.register
class QualityMetric(CvParameter):
    """
    QualityMetric Object representation is passed for its more concrete derivatives

    """
    pass
    # def __init__(self, cvRef: str="",
    #                 accession: str="",
    #                 name: str="",
    #                 description: str="",
    #                 value: Union[int,str,float,IntVector,StringVector,FloatVector,IntMatrix,StringMatrix,FloatMatrix,Table, None]=None,  # here we could clamp down on allowed value types
    #                 unit: str=""):
    #     super().__init__(cvRef, accession, name, description, value, unit)  # optional, this will set None to optional omitted arguments
    # implementation: this is a different object class because we want to make
    # semantical distinctions between pure metrics and generic CvParams

@JsonSerialisable.register
class BaseQuality(JsonObject):
    """
    BaseQuality Object representation for mzQC schema type BaseQuality

    """
    def __init__(self, metadata: MetaDataParameters=None,
                    qualityMetrics: List[QualityMetric]=None):
        self.metadata = metadata  # required
        self.qualityMetrics = [] if qualityMetrics is None else qualityMetrics  # required,

@JsonSerialisable.register
class RunQuality(BaseQuality):
    """
    QualityMetric Object representation is passed for its more general basis

    """
    pass

@JsonSerialisable.register
class SetQuality(BaseQuality):
    """
    SetQuality Object representation is passed for its more general basis

    """
    pass

@JsonSerialisable.register
class MzQcFile(JsonObject):
    """
    MzQcFile Object representation for mzQC schema type MzQcFile

    """
    def __init__(self, creationDate: Union[datetime,str] = datetime.now().replace(microsecond=0),
                    version: str = "1.0.0",
                    contactName: str = "", contactAddress: str = "", description: str = "",
                    runQualities: List[RunQuality]=None,
                    setQualities: List[SetQuality]=None,
                    controlledVocabularies: List[ControlledVocabulary]=None
                    ):
        self.creationDate = JsonSerialisable.time_helper(creationDate) if isinstance(creationDate, str) else creationDate  # required
        self.version = version  # required
        self.contactName = contactName  # optional
        self.contactAddress = contactAddress  # optional
        self.description = description  # optional
        self.runQualities = [] if runQualities is None else runQualities  # either or set required
        self.setQualities = [] if setQualities is None else setQualities  # either or run required
        self.controlledVocabularies = [] if controlledVocabularies is None else controlledVocabularies  # required
